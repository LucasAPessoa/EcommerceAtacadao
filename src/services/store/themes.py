from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeInfo:
    key: str
    name: str
    description: str


DEFAULT_THEME = "gondola"

THEMES: dict[str, ThemeInfo] = {
    "gondola": ThemeInfo(
        key="gondola",
        name="Gôndola",
        description="Vitrine de varejo com grade de produtos densa e cor de marca em destaque.",
    ),
}
