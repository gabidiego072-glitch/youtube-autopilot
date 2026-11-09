"""On-screen texts (billboards, the café TV and menu) in the video's language. No Blender imports."""

# Language of the on-screen texts ("es" or "en"); the director sets it from the scene spec.
LANG = "es"
HEADLINE = ""  # the breaking-news line of this scene (the TV in the café), if the story gives one
TEXTS = {
    "magic_1": ("EL GRAN ACTO", "THE GREAT"),
    "magic_2": ("DE DESAPARICIÓN", "VANISHING ACT"),
    "alert_1": ("ALERTA", "ALERT"),
    "alert_2": ("QUÉDATE EN CASA", "STAY INSIDE"),
    "live": ("EN DIRECTO", "LIVE"),
    "news_bar": ("ÚLTIMA HORA: BROTE EN NUEVA YORK", "BREAKING: OUTBREAK IN NEW YORK"),
    "smile": ("SONRÍE,\nESTÁS EN\nNUEVA YORK", "SMILE,\nYOU'RE IN\nNEW YORK"),
    "soda_1": ("FRESCA", "FRESH"),
    "soda_2": ("SABOR NYC", "TASTE NYC"),
    "breaking_1": ("ÚLTIMA HORA", "BREAKING NEWS"),
    "breaking_2": ("BROTE EN\nNUEVA YORK", "OUTBREAK IN\nNEW YORK"),
    "menu": ("CAFÉ  2$\nLATTE  3$\nBAGEL  2$", "COFFEE  2$\nLATTE  3$\nBAGEL  2$"),
}


def tr(key: str) -> str:
    """An on-screen text in the video's language (Spanish if the language is not translated)."""
    es, en = TEXTS[key]
    return en if LANG == "en" else es
