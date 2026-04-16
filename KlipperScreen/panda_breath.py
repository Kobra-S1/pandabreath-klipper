import logging

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    """KlipperScreen panel for Panda Breath control.

    Features:
    - Heating page: chamber target control
    - Auto page: native Panda auto mode target/threshold configuration
    - Drying page: drying temperature/time start+stop and remaining time display
    - Live status from Moonraker printer.objects.query (panda_breath + heater_generic)
    """

    MIN_TARGET = 0
    MAX_TARGET = 80

    # (temp_c, hours) per material preset
    PRESETS = {
        "PLA":  (45, 6),
        "PETG": (65, 6),
        "ABS":  (70, 4),
        "ASA":  (70, 4),
    }

    def __init__(self, screen, title):
        super().__init__(screen, title)

        self.pb_status = {}
        self.hg_status = {}
        self.current_view = "climate"
        self._poll_timer = None
        self.number_dialog = None
        self.number_entry = None
        self.number_apply = None
        self.number_min = None
        self.number_max = None
        self.number_error = None
        self.number_replace_on_next_digit = False
        self._css_provider = None

        # UI state vars
        self.climate_target = 45
        self.auto_enabled = False
        self.auto_target = 45
        self.auto_filtertemp = 30
        self.auto_hotbedtemp = 80
        self.dry_temp = 55
        self.dry_hours = 6
        self._auto_switch_syncing = False

        self._add_custom_css()
        self._build_ui()
        self._update_target_label()
        self._update_auto_labels()
        self._sync_auto_switch(self.auto_enabled)
        self._update_dry_labels()
        self._start_polling()

    def activate(self):
        self._start_polling()
        GLib.timeout_add(150, self._refresh_once)

    def deactivate(self):
        if self._poll_timer is not None:
            GLib.source_remove(self._poll_timer)
            self._poll_timer = None
        self._close_number_dialog()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.lbl_status = Gtk.Label(label="Current Temp: -- C   Target: -- C   Mode: --   Power: --")
        self.lbl_status.set_xalign(0.5)
        self.lbl_status.set_hexpand(True)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        self.stack.add_named(self._scrollable(self._build_climate_page()), "climate")
        self.stack.add_named(self._scrollable(self._build_auto_page()), "auto")
        self.stack.add_named(self._scrollable(self._build_drying_page()), "drying")

        # Page switch buttons live at the bottom to keep status and controls first.
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_climate = self._gtk.Button("heater", "Heating", "color1", .66, Gtk.PositionType.LEFT, 1)
        self.btn_auto = self._gtk.Button(None, "Auto", "color3", .66, Gtk.PositionType.LEFT, 1)
        self.btn_drying = self._gtk.Button("clock", "Drying", "color2", .66, Gtk.PositionType.LEFT, 1)
        for btn in (self.btn_climate, self.btn_auto, self.btn_drying):
            btn.set_vexpand(False)
            btn.set_size_request(-1, max(int(self._gtk.font_size * 2.6), 42))
            btn.get_style_context().add_class("panda_nav_button")
        self.btn_climate.connect("clicked", self._switch_view, "climate")
        self.btn_auto.connect("clicked", self._switch_view, "auto")
        self.btn_drying.connect("clicked", self._switch_view, "drying")
        nav.pack_start(self.btn_climate, True, True, 0)
        nav.pack_start(self.btn_auto, True, True, 0)
        nav.pack_start(self.btn_drying, True, True, 0)

        root.pack_start(self.lbl_status, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
        root.pack_start(nav, False, False, 0)

        self.content.add(root)

    def _scrollable(self, child):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_vexpand(True)
        scroll.add(child)
        return scroll

    def _status_grid(self, labels):
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(2)
        grid.set_hexpand(True)
        for idx, lbl in enumerate(labels):
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            grid.attach(lbl, idx % 2, idx // 2, 1, 1)
        return grid

    def _two_column_row(self, left, right):
        row = Gtk.Grid()
        row.set_column_spacing(6)
        row.set_column_homogeneous(True)
        row.set_hexpand(True)
        left.set_hexpand(True)
        right.set_hexpand(True)
        row.attach(left, 0, 0, 1, 1)
        row.attach(right, 1, 0, 1, 1)
        return row

    def _add_custom_css(self):
        css = b"""
        button.panda_numpad_button {
            border: 1px solid #888;
            border-radius: 6px;
            padding: 2px;
        }
        button.panda_numpad_button:active {
            border-color: #aaa;
        }
        entry.panda_number_entry {
            border: 1px solid #888;
            border-radius: 6px;
            padding: 8px;
        }
        button.panda_nav_button {
            padding: 2px 8px;
            min-height: 0;
        }
        """
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER,
            )

    def _build_climate_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Target set controls
        row_target = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_t_minus = self._gtk.Button("decrease", "-", "color4")
        self.btn_t_plus = self._gtk.Button("increase", "+", "color4")
        self.btn_target_set = self._gtk.Button(None, self._target_label(), "color3")

        self.btn_t_minus.connect("clicked", self._adjust_climate_target, -1)
        self.btn_t_plus.connect("clicked", self._adjust_climate_target, 1)
        self.btn_target_set.connect("clicked", self._show_target_input)

        row_target.pack_start(self.btn_t_minus, False, False, 0)
        row_target.pack_start(self.btn_target_set, True, True, 0)
        row_target.pack_start(self.btn_t_plus, False, False, 0)

        row_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_set = self._gtk.Button("heater", "Set Target", "color3")
        self.btn_off = self._gtk.Button("shutdown", "Heating Off", "color1")
        self.btn_set.connect("clicked", self._cmd_set_target)
        self.btn_off.connect("clicked", self._cmd_off)

        row_actions.pack_start(self.btn_set, True, True, 0)
        row_actions.pack_start(self.btn_off, True, True, 0)

        page.pack_start(row_target, False, False, 0)
        page.pack_start(row_actions, False, False, 0)
        return page

    def _build_drying_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.lbl_dry_active = Gtk.Label(label="Drying: --")
        self.lbl_dry_temp = Gtk.Label(label="Dry Temp: -- C")
        self.lbl_dry_time = Gtk.Label(label="Dry Time: -- h")
        self.lbl_dry_remaining = Gtk.Label(label="Remaining: --")

        status_box = self._status_grid((
            self.lbl_dry_active, self.lbl_dry_temp, self.lbl_dry_time, self.lbl_dry_remaining
        ))

        # Drying temp controls
        temp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_temp_minus = self._gtk.Button("decrease", "Temp -", "color4")
        btn_temp_plus = self._gtk.Button("increase", "Temp +", "color4")
        self.btn_dry_temp_set = self._gtk.Button(None, self._dry_temp_label(), "color3")
        btn_temp_minus.connect("clicked", self._adjust_dry_temp, -1)
        btn_temp_plus.connect("clicked", self._adjust_dry_temp, 1)
        self.btn_dry_temp_set.connect("clicked", self._show_dry_temp_input)
        temp_row.pack_start(btn_temp_minus, False, False, 0)
        temp_row.pack_start(self.btn_dry_temp_set, True, True, 0)
        temp_row.pack_start(btn_temp_plus, False, False, 0)

        # Drying hours controls
        hours_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_h_minus = self._gtk.Button("decrease", "Hours -", "color4")
        btn_h_plus = self._gtk.Button("increase", "Hours +", "color4")
        self.btn_dry_hours_set = self._gtk.Button(None, self._dry_hours_label(), "color3")
        btn_h_minus.connect("clicked", self._adjust_dry_hours, -1)
        btn_h_plus.connect("clicked", self._adjust_dry_hours, 1)
        self.btn_dry_hours_set.connect("clicked", self._show_dry_hours_input)
        hours_row.pack_start(btn_h_minus, False, False, 0)
        hours_row.pack_start(self.btn_dry_hours_set, True, True, 0)
        hours_row.pack_start(btn_h_plus, False, False, 0)

        row_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_start = self._gtk.Button("resume", "Start Drying", "color2")
        btn_stop = self._gtk.Button("stop", "Stop Drying", "color1")
        btn_start.connect("clicked", self._cmd_dry_start)
        btn_stop.connect("clicked", self._cmd_dry_stop)
        row_actions.pack_start(btn_start, True, True, 0)
        row_actions.pack_start(btn_stop, True, True, 0)

        # Material presets row
        presets_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for material, (t, h) in self.PRESETS.items():
            btn = self._gtk.Button(None, material, "color3")
            btn.connect("clicked", self._apply_preset, material)
            presets_row.pack_start(btn, True, True, 0)

        page.pack_start(status_box, False, False, 0)
        page.pack_start(row_actions, False, False, 0)
        page.pack_start(self._two_column_row(temp_row, hours_row), False, False, 0)
        page.pack_start(presets_row, False, False, 0)
        return page

    def _build_auto_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.lbl_auto_active = Gtk.Label(label="Auto Mode: --")
        self.lbl_auto_target_status = Gtk.Label(label="Target Chamber: -- C")
        self.lbl_auto_filter_status = Gtk.Label(label="Filter Threshold: -- C")
        self.lbl_auto_hotbed_status = Gtk.Label(label="Heater Threshold: -- C")
        status_box = self._status_grid((
            self.lbl_auto_active,
            self.lbl_auto_target_status,
            self.lbl_auto_filter_status,
            self.lbl_auto_hotbed_status,
        ))

        toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toggle_label = Gtk.Label(label="Enable Auto Mode")
        toggle_label.set_xalign(0)
        toggle_label.set_hexpand(True)
        self.auto_switch = Gtk.Switch()
        self.auto_switch.set_halign(Gtk.Align.END)
        self.auto_switch.connect("notify::active", self._on_auto_switch_changed)
        toggle_row.pack_start(toggle_label, True, True, 0)
        toggle_row.pack_end(self.auto_switch, False, False, 0)

        target_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_auto_target_minus = self._gtk.Button("decrease", "-", "color4")
        btn_auto_target_plus = self._gtk.Button("increase", "+", "color4")
        self.btn_auto_target_set = self._gtk.Button(None, self._auto_target_label(), "color3")
        btn_auto_target_minus.connect("clicked", self._adjust_auto_target, -1)
        btn_auto_target_plus.connect("clicked", self._adjust_auto_target, 1)
        self.btn_auto_target_set.connect("clicked", self._show_auto_target_input)
        target_row.pack_start(btn_auto_target_minus, False, False, 0)
        target_row.pack_start(self.btn_auto_target_set, True, True, 0)
        target_row.pack_start(btn_auto_target_plus, False, False, 0)

        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_auto_filter_minus = self._gtk.Button("decrease", "-", "color4")
        btn_auto_filter_plus = self._gtk.Button("increase", "+", "color4")
        self.btn_auto_filter_set = self._gtk.Button(None, self._auto_filter_label(), "color3")
        btn_auto_filter_minus.connect("clicked", self._adjust_auto_filtertemp, -1)
        btn_auto_filter_plus.connect("clicked", self._adjust_auto_filtertemp, 1)
        self.btn_auto_filter_set.connect("clicked", self._show_auto_filter_input)
        filter_row.pack_start(btn_auto_filter_minus, False, False, 0)
        filter_row.pack_start(self.btn_auto_filter_set, True, True, 0)
        filter_row.pack_start(btn_auto_filter_plus, False, False, 0)

        hotbed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_auto_hotbed_minus = self._gtk.Button("decrease", "-", "color4")
        btn_auto_hotbed_plus = self._gtk.Button("increase", "+", "color4")
        self.btn_auto_hotbed_set = self._gtk.Button(None, self._auto_hotbed_label(), "color3")
        btn_auto_hotbed_minus.connect("clicked", self._adjust_auto_hotbedtemp, -1)
        btn_auto_hotbed_plus.connect("clicked", self._adjust_auto_hotbedtemp, 1)
        self.btn_auto_hotbed_set.connect("clicked", self._show_auto_hotbed_input)
        hotbed_row.pack_start(btn_auto_hotbed_minus, False, False, 0)
        hotbed_row.pack_start(self.btn_auto_hotbed_set, True, True, 0)
        hotbed_row.pack_start(btn_auto_hotbed_plus, False, False, 0)

        row_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_apply = self._gtk.Button("complete", "Apply Auto", "color3")
        btn_disable = self._gtk.Button("shutdown", "Auto Off", "color1")
        btn_apply.connect("clicked", self._cmd_auto_apply)
        btn_disable.connect("clicked", self._cmd_auto_off)
        row_actions.pack_start(btn_apply, True, True, 0)
        row_actions.pack_start(btn_disable, True, True, 0)

        page.pack_start(status_box, False, False, 0)
        page.pack_start(toggle_row, False, False, 0)
        page.pack_start(target_row, False, False, 0)
        page.pack_start(filter_row, False, False, 0)
        page.pack_start(hotbed_row, False, False, 0)
        page.pack_start(row_actions, False, False, 0)
        return page

    def _switch_view(self, _btn, view_name):
        self.current_view = view_name
        self.stack.set_visible_child_name(view_name)

    def _target_label(self):
        return f"Set Target: {self.climate_target} C"

    def _update_target_label(self):
        self.btn_target_set.set_label(self._target_label())

    def _auto_target_label(self):
        return f"Target Chamber: {self.auto_target} C"

    def _auto_filter_label(self):
        return f"Filter Threshold: {self.auto_filtertemp} C"

    def _auto_hotbed_label(self):
        return f"Heater Threshold: {self.auto_hotbedtemp} C"

    def _update_auto_labels(self):
        if hasattr(self, "btn_auto_target_set"):
            self.btn_auto_target_set.set_label(self._auto_target_label())
        if hasattr(self, "btn_auto_filter_set"):
            self.btn_auto_filter_set.set_label(self._auto_filter_label())
        if hasattr(self, "btn_auto_hotbed_set"):
            self.btn_auto_hotbed_set.set_label(self._auto_hotbed_label())
        if hasattr(self, "lbl_auto_target_status"):
            self.lbl_auto_target_status.set_text(f"Target Chamber: {self.auto_target} C")
        if hasattr(self, "lbl_auto_filter_status"):
            self.lbl_auto_filter_status.set_text(f"Filter Threshold: {self.auto_filtertemp} C")
        if hasattr(self, "lbl_auto_hotbed_status"):
            self.lbl_auto_hotbed_status.set_text(f"Heater Threshold: {self.auto_hotbedtemp} C")

    def _dry_temp_label(self):
        return f"{self.dry_temp} C"

    def _dry_hours_label(self):
        return f"{self.dry_hours} h"

    def _update_dry_labels(self):
        self.btn_dry_temp_set.set_label(self._dry_temp_label())
        self.btn_dry_hours_set.set_label(self._dry_hours_label())

    def _adjust_climate_target(self, _btn, delta):
        self.climate_target = int(max(self.MIN_TARGET, min(self.MAX_TARGET, self.climate_target + delta)))
        self._update_target_label()

    def _show_target_input(self, btn):
        self._show_number_input(
            btn,
            "Set Target",
            self.climate_target,
            self.MIN_TARGET,
            self.MAX_TARGET,
            self._set_climate_target,
            "Target",
        )

    def _show_auto_target_input(self, btn):
        self._show_number_input(
            btn,
            "Set Auto Target",
            self.auto_target,
            self.MIN_TARGET,
            self.MAX_TARGET,
            self._set_auto_target,
            "Auto target",
        )

    def _show_auto_filter_input(self, btn):
        self._show_number_input(
            btn,
            "Set Filter Threshold",
            self.auto_filtertemp,
            0,
            120,
            self._set_auto_filtertemp,
            "Filter threshold",
        )

    def _show_auto_hotbed_input(self, btn):
        self._show_number_input(
            btn,
            "Set Heater Threshold",
            self.auto_hotbedtemp,
            0,
            120,
            self._set_auto_hotbedtemp,
            "Heater threshold",
        )

    def _show_dry_temp_input(self, btn):
        self._show_number_input(
            btn,
            "Set Drying Temperature",
            self.dry_temp,
            self.MIN_TARGET,
            self.MAX_TARGET,
            self._set_dry_temp,
            "Drying temperature",
        )

    def _show_dry_hours_input(self, btn):
        self._show_number_input(
            btn,
            "Set Drying Hours",
            self.dry_hours,
            1,
            12,
            self._set_dry_hours,
            "Drying hours",
        )

    def _show_number_input(self, _btn, title, value, min_value, max_value, apply_cb, error_label):
        if self.number_dialog is not None:
            self.number_dialog.present()
            return

        self.number_apply = apply_cb
        self.number_min = min_value
        self.number_max = max_value
        self.number_error = error_label

        content = self._build_number_input(value)
        self.number_dialog = Gtk.Dialog(
            title=title,
            modal=True,
            transient_for=self._screen,
            default_width=self._gtk.width,
            default_height=self._gtk.height,
        )
        self.number_dialog.set_size_request(self._gtk.width, self._gtk.height)
        if not self._screen.windowed:
            self.number_dialog.fullscreen()
        self.number_dialog.get_style_context().add_class("dialog")

        content_area = self.number_dialog.get_content_area()
        content_area.set_margin_start(10)
        content_area.set_margin_end(5)
        content_area.set_margin_top(5)
        content_area.set_margin_bottom(0)
        content_area.add(content)

        self.number_dialog.show_all()
        self._gtk.set_cursor(show=self._screen.show_cursor, window=self.number_dialog.get_window())
        self._screen.dialogs.append(self.number_dialog)
        GLib.idle_add(self._focus_number_entry)

    def _number_dialog_response(self, dialog, _response_id):
        self.number_dialog = None
        self.number_entry = None
        self.number_apply = None
        self.number_min = None
        self.number_max = None
        self.number_error = None
        self.number_replace_on_next_digit = False
        self._gtk.remove_dialog(dialog)

    def _close_number_dialog(self, _widget=None):
        dialog = self.number_dialog
        self.number_dialog = None
        self.number_entry = None
        self.number_apply = None
        self.number_min = None
        self.number_max = None
        self.number_error = None
        self.number_replace_on_next_digit = False
        if dialog is not None:
            self._gtk.remove_dialog(dialog)

    def _build_number_input(self, value):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        screen = Gdk.Screen.get_default()
        screen_w = screen.get_width() if screen else 800
        screen_h = screen.get_height() if screen else 480
        left_width = int(screen_w * 0.62)
        right_width = int(screen_w * 0.30)
        grid_spacing = 6
        key_width = int((left_width - (grid_spacing * 2)) / 3)
        key_height = int(max(64, min((screen_h * 0.88 - (grid_spacing * 3)) / 4, 155)))

        self.number_entry = Gtk.Entry()
        self.number_entry.set_max_length(5)
        self.number_entry.set_alignment(0.5)
        self.number_entry.set_text(str(value))
        self.number_entry.set_hexpand(True)
        self.number_entry.set_vexpand(False)
        self.number_entry.set_size_request(right_width, int(key_height * 0.75))
        self.number_entry.get_style_context().add_class("panda_number_entry")
        self.number_entry.connect("activate", self._apply_number_entry)
        self.number_replace_on_next_digit = True

        numpad = Gtk.Grid(row_homogeneous=False, column_homogeneous=False)
        numpad.set_direction(Gtk.TextDirection.LTR)
        keys = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "B", "0", ".")

        for idx, label in enumerate(keys):
            if label == "B":
                btn = Gtk.Button(label="Del")
                btn.connect("clicked", self._backspace_number_entry)
            else:
                btn = Gtk.Button(label=label)
                btn.connect("clicked", self._append_number_entry_char, label)
            btn.get_style_context().add_class("panda_numpad_button")
            btn.set_size_request(key_width, key_height)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            numpad.attach(btn, idx % 3, idx // 3, 1, 1)

        numpad.set_row_spacing(grid_spacing)
        numpad.set_column_spacing(grid_spacing)
        numpad.set_halign(Gtk.Align.CENTER)
        numpad.set_valign(Gtk.Align.START)

        btn_row = Gtk.Box(spacing=6)
        cancel_btn = self._gtk.Button("cancel", scale=.66)
        apply_btn = self._gtk.Button("complete", style="color1")
        cancel_btn.connect("clicked", self._close_number_dialog)
        apply_btn.connect("clicked", self._apply_number_entry)
        cancel_btn.set_size_request(int((right_width - 6) / 2), int(key_height * 0.75))
        apply_btn.set_size_request(int((right_width - 6) / 2), int(key_height * 0.75))
        btn_row.pack_start(cancel_btn, True, True, 0)
        btn_row.pack_start(apply_btn, True, True, 0)
        btn_row.set_size_request(right_width, -1)

        close_btn = self._gtk.Button(None, "Close", "color4")
        close_btn.connect("clicked", self._close_number_dialog)
        close_btn.set_size_request(right_width, int(key_height * 0.75))

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left_box.set_size_request(left_width, -1)
        left_box.pack_start(numpad, False, False, 0)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.set_size_request(right_width, -1)
        right_box.pack_start(self.number_entry, False, False, 0)
        right_box.pack_start(btn_row, False, False, 0)
        right_box.pack_start(close_btn, False, False, 0)

        box.pack_start(left_box, False, False, 0)
        box.pack_start(right_box, False, False, 0)
        box.set_valign(Gtk.Align.START)

        self._focus_number_entry()
        return box

    def _focus_number_entry(self):
        if self.number_entry is None:
            return False
        self.number_entry.grab_focus()
        self.number_entry.select_region(0, -1)
        self.number_replace_on_next_digit = True
        return False

    def _append_number_entry_char(self, _btn, char):
        if self.number_entry is None:
            return
        if self.number_replace_on_next_digit:
            self.number_entry.set_text(char)
            self.number_entry.set_position(len(char))
            self.number_replace_on_next_digit = False
            return
        text = self.number_entry.get_text()
        if len(text) >= 5:
            return
        bounds = self.number_entry.get_selection_bounds()
        if bounds:
            start, end = bounds
            text = text[:start] + char + text[end:]
            cursor_pos = start + len(char)
        else:
            cursor_pos = len(text) + len(char)
            text = text + char
        self.number_entry.set_text(text)
        self.number_entry.set_position(cursor_pos)

    def _backspace_number_entry(self, _btn=None):
        if self.number_entry is None:
            return
        if self.number_replace_on_next_digit:
            self.number_entry.set_text("")
            self.number_replace_on_next_digit = False
            return
        text = self.number_entry.get_text()
        bounds = self.number_entry.get_selection_bounds()
        if bounds:
            start, end = bounds
            text = text[:start] + text[end:]
            self.number_entry.set_text(text)
            self.number_entry.set_position(start)
        elif text:
            text = text[:-1]
            self.number_entry.set_text(text)
            self.number_entry.set_position(len(text))

    def _apply_number_entry(self, _widget=None):
        if self.number_entry is None or self.number_apply is None:
            return
        try:
            value = int(round(float(self.number_entry.get_text())))
        except (TypeError, ValueError):
            self._screen.show_popup_message("Invalid number")
            return

        if value < self.number_min or value > self.number_max:
            self._screen.show_popup_message(
                f"{self.number_error} must be between {self.number_min} and {self.number_max}"
            )
            self._focus_number_entry()
            return

        self.number_apply(value)
        self._close_number_dialog()

    def _set_climate_target(self, target):
        self.climate_target = target
        self._update_target_label()

    def _set_auto_target(self, target):
        self.auto_target = target
        self._update_auto_labels()

    def _set_auto_filtertemp(self, filtertemp):
        self.auto_filtertemp = filtertemp
        self._update_auto_labels()

    def _set_auto_hotbedtemp(self, hotbedtemp):
        self.auto_hotbedtemp = hotbedtemp
        self._update_auto_labels()

    def _set_dry_temp(self, temp):
        self.dry_temp = temp
        self._update_dry_labels()

    def _set_dry_hours(self, hours):
        self.dry_hours = hours
        self._update_dry_labels()

    def _apply_preset(self, _btn, material):
        t, h = self.PRESETS.get(material, (self.dry_temp, self.dry_hours))
        self.dry_temp = t
        self.dry_hours = h
        self._update_dry_labels()

    def _adjust_dry_temp(self, _btn, delta):
        self.dry_temp = int(max(self.MIN_TARGET, min(self.MAX_TARGET, self.dry_temp + delta)))
        self._update_dry_labels()

    def _adjust_dry_hours(self, _btn, delta):
        self.dry_hours = int(max(1, min(12, self.dry_hours + delta)))
        self._update_dry_labels()

    def _adjust_auto_target(self, _btn, delta):
        self.auto_target = int(max(self.MIN_TARGET, min(self.MAX_TARGET, self.auto_target + delta)))
        self._update_auto_labels()

    def _adjust_auto_filtertemp(self, _btn, delta):
        self.auto_filtertemp = int(max(0, min(120, self.auto_filtertemp + delta)))
        self._update_auto_labels()

    def _adjust_auto_hotbedtemp(self, _btn, delta):
        self.auto_hotbedtemp = int(max(0, min(120, self.auto_hotbedtemp + delta)))
        self._update_auto_labels()

    def _send_gcode(self, gcode):
        try:
            self._screen._ws.klippy.gcode_script(gcode)
            return True
        except Exception as exc:
            logging.error("PandaBreath panel gcode error: %s", exc)
            self._screen.show_popup_message("Failed to send command to Klipper")
            return False

    def _cmd_set_target(self, _btn):
        self._send_gcode(f"SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={self.climate_target}")

    def _cmd_off(self, _btn):
        self._send_gcode("SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0")

    def _cmd_auto_apply(self, _btn=None):
        enable = 1 if self.auto_enabled else 0
        self._send_gcode(
            "PANDA_BREATH_AUTO "
            f"ENABLE={enable} "
            f"TARGET={self.auto_target} "
            f"FILTERTEMP={self.auto_filtertemp} "
            f"HOTBEDTEMP={self.auto_hotbedtemp}"
        )

    def _cmd_auto_off(self, _btn=None):
        self._sync_auto_switch(False)
        self._send_gcode(
            "PANDA_BREATH_AUTO "
            f"ENABLE=0 TARGET={self.auto_target} "
            f"FILTERTEMP={self.auto_filtertemp} "
            f"HOTBEDTEMP={self.auto_hotbedtemp}"
        )

    def _cmd_dry_start(self, _btn):
        self._send_gcode(f"PANDA_BREATH_DRY_START TEMP={self.dry_temp} HOURS={self.dry_hours}")

    def _cmd_dry_stop(self, _btn):
        self._send_gcode("PANDA_BREATH_DRY_STOP")

    def _on_auto_switch_changed(self, switch, _param):
        if self._auto_switch_syncing:
            return
        self.auto_enabled = bool(switch.get_active())
        self._cmd_auto_apply()

    def _sync_auto_switch(self, active):
        self.auto_enabled = bool(active)
        if hasattr(self, "lbl_auto_active"):
            self.lbl_auto_active.set_text(f"Auto Mode: {'ACTIVE' if self.auto_enabled else 'IDLE'}")
        if not hasattr(self, "auto_switch"):
            return
        self._auto_switch_syncing = True
        self.auto_switch.set_active(self.auto_enabled)
        self._auto_switch_syncing = False

    def _start_polling(self):
        if self._poll_timer is not None:
            return
        self._poll_timer = GLib.timeout_add_seconds(2, self._poll_status)

    def _refresh_once(self):
        self._poll_status()
        return False

    def _poll_status(self):
        try:
            direct_ws = getattr(getattr(getattr(self, "_screen", None), "_ws", None), "klippy", None)
            direct_ws = getattr(direct_ws, "_ws", None)
            if not callable(getattr(direct_ws, "send_method", None)):
                return True

            objects = {
                "panda_breath": None,
                "heater_generic panda_breath": None,
            }

            def _cb(response, *_):
                try:
                    result = (response or {}).get("result", {})
                    status = (result or {}).get("status", {})
                    pb = status.get("panda_breath")
                    hg = status.get("heater_generic panda_breath")
                    if isinstance(pb, dict):
                        self.pb_status = pb
                    if isinstance(hg, dict):
                        self.hg_status = hg
                    self._update_ui()
                except Exception as exc:
                    logging.debug("PandaBreath panel status callback error: %s", exc)

            direct_ws.send_method("printer.objects.query", {"objects": objects}, _cb)
        except Exception as exc:
            logging.debug("PandaBreath panel poll error: %s", exc)
        return True

    def process_update(self, action, data):
        # Live Moonraker status updates (if available)
        if action != "notify_status_update" or not isinstance(data, dict):
            return
        if "panda_breath" in data and isinstance(data["panda_breath"], dict):
            self.pb_status.update(data["panda_breath"])
        if "heater_generic panda_breath" in data and isinstance(data["heater_generic panda_breath"], dict):
            self.hg_status.update(data["heater_generic panda_breath"])
        self._update_ui()

    def _update_ui(self):
        pb = self.pb_status or {}
        hg = self.hg_status or {}

        work_mode = int(pb.get("work_mode", 0) or 0)
        cur_temp = pb.get("temperature", hg.get("temperature", 0.0))
        power = bool(pb.get("work_on", False))
        auto_target = int(pb.get("auto_target", self.auto_target) or 0)
        target = auto_target if work_mode == 1 else hg.get("target", pb.get("target", 0.0))
        dry_active = bool(pb.get("filament_drying_active", False))
        mode = self._display_mode(work_mode, dry_active, target, power)

        self.lbl_status.set_text(
            f"Current Temp: {float(cur_temp):.1f} C   "
            f"Target: {float(target):.1f} C   "
            f"Mode: {mode}   "
            f"Power: {'ON' if power else 'OFF'}"
        )

        self.auto_target = auto_target
        self.auto_filtertemp = int(pb.get("auto_filtertemp", self.auto_filtertemp) or 0)
        self.auto_hotbedtemp = int(pb.get("auto_hotbedtemp", self.auto_hotbedtemp) or 0)
        auto_enabled = bool(pb.get("auto_enabled", work_mode == 1 and power))
        self._sync_auto_switch(auto_enabled)
        self._update_auto_labels()
        self.lbl_auto_active.set_text(f"Auto Mode: {'ACTIVE' if auto_enabled else 'IDLE'}")
        self.lbl_auto_target_status.set_text(f"Target Chamber: {self.auto_target} C")
        self.lbl_auto_filter_status.set_text(f"Filter Threshold: {self.auto_filtertemp} C")
        self.lbl_auto_hotbed_status.set_text(f"Heater Threshold: {self.auto_hotbedtemp} C")

        dry_temp = int(pb.get("filament_temp", 0) or 0)
        dry_time = int(pb.get("filament_timer", 0) or 0)
        remaining = int(pb.get("remaining_seconds", 0) or 0)

        self.lbl_dry_active.set_text(f"Drying: {'ACTIVE' if dry_active else 'IDLE'}")
        self.lbl_dry_temp.set_text(f"Dry Temp: {dry_temp} C")
        self.lbl_dry_time.set_text(f"Dry Time: {dry_time} h")
        self.lbl_dry_remaining.set_text(f"Remaining: {self._fmt_time(remaining)}")

    def _display_mode(self, work_mode, dry_active, target, power):
        if dry_active:
            return "Drying"
        if work_mode == 1:
            return "Auto"
        try:
            target = float(target)
        except Exception:
            target = 0
        if power or target > 0:
            return "Heating"
        return "Idle"

    @staticmethod
    def _fmt_time(total_seconds):
        try:
            sec = int(total_seconds)
        except Exception:
            return "--"
        if sec <= 0:
            return "00:00:00"
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
