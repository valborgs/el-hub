# -*- coding: utf-8 -*-
"""공용 테마 색상 팔레트.

네 프로젝트가 쓰던 팔레트의 합집합을 단일 소스로 통합한다.

- 공통 키: bg, surface, surface_alt, text, text_muted, border,
           accent, accent_hover, accent_fg
- backup-tool 전용: btn_bg (찾아보기 버튼 배경)
- 허브 상태색: green (실행/정상 도트), red (오류)
"""

PALETTE: dict[str, dict[str, str]] = {
    "light": dict(
        bg="#EFEBE3",    surface="#F5F2EB",  surface_alt="#EBE7DE",
        text="#2A2926",  text_muted="#8A857B", border="#D9D3C7",
        accent="#7B8A6E", accent_hover="#6B7A5E", accent_fg="#FFFFFF",
        btn_bg="#C4BDB0",
        green="#5A7A5A", red="#9C3F3F",
    ),
    "dark": dict(
        bg="#1A1916",    surface="#24221E",  surface_alt="#15140F",
        text="#E8E4DA",  text_muted="#8A857B", border="#2F2D29",
        accent="#94A484", accent_hover="#A4B494", accent_fg="#1A1916",
        btn_bg="#3F3D38",
        green="#7CB47C", red="#D08585",
    ),
}

LOG_COLORS: dict[str, dict[str, str]] = {
    "light": dict(info="#2A2926", success="#5A6B4E", warning="#A07A2A", error="#9C3F3F"),
    "dark":  dict(info="#E8E4DA", success="#A4B494", warning="#D6B86A", error="#D08585"),
}

# 도움말(HelpDialog) HTML 은 테마와 무관하게 항상 밝은 배경을 쓰므로 고정 강조색을 둔다.
HELP_ACCENT = "#7B8A6E"
HELP_MUTED  = "#8A857B"
