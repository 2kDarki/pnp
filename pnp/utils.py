"""Module to keep communication with externals isolated"""

# ======================= STANDARDS =======================
import os

# ==================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text, style_text as color
from tuikit.textools import transmit as _transmit, pathit
from tuikit.logictools import any_in
from tuikit.listools import choose

# ======================== LOCALS =========================
from ._constants import *


def to_list(array: list) -> str:
    if not isinstance(array, list): err(array, "list")
    text = ""   
    for i, item in enumerate(array):
        pfx    = f"      {i+1}."
        indent = len(pfx) + 2
        text  += pfx + " " + wrap_text(f"{item}\n", indent, 
                inline=True, order=pfx)    
    return text

def wrap(text:str) -> str:
    return wrap_text(text, I, inline=True, order=APP)


def transmit(*text: tuple[str], fg:str = PROMPT) -> None:
    print(PNP, end="")
    _transmit(*text, speed=SPEED, hold=HOLD, hue=fg)


def intent(prompt, condition, action="exit"):
    transmit(prompt)
    _intent = input(CURSOR).strip().lower(); print()
    _intent = _intent[0] if _intent else "n"
    if action == "return": return _intent == condition
    if _intent != condition: sys.exit(1)
