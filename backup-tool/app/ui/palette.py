# -*- coding: utf-8 -*-
"""테마 색상 팔레트 정의."""

PALETTE: dict[str, dict[str, str]] = {
    "light": dict(
        bg="#EFEBE3",    surface="#F5F2EB",  surface_alt="#EBE7DE",
        text="#2A2926",  text_muted="#8A857B", border="#D9D3C7",
        accent="#7B8A6E", accent_hover="#6B7A5E", accent_fg="#FFFFFF",
        btn_bg="#C4BDB0",
    ),
    "dark": dict(
        bg="#1A1916",    surface="#24221E",  surface_alt="#15140F",
        text="#E8E4DA",  text_muted="#8A857B", border="#2F2D29",
        accent="#94A484", accent_hover="#A4B494", accent_fg="#1A1916",
        btn_bg="#3F3D38",
    ),
}

LOG_COLORS: dict[str, dict[str, str]] = {
    "light": dict(info="#2A2926", success="#5A6B4E", warning="#A07A2A", error="#9C3F3F"),
    "dark":  dict(info="#E8E4DA", success="#A4B494", warning="#D6B86A", error="#D08585"),
}
