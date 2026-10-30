"""Tema visual e componentes comuns da interface (tabela, dica, ícones).

Parte do programa Levantamento de Materiais (Ceneged)."""

import base64
import io
import tkinter as tk
from tkinter import ttk
from PIL import Image
from PIL import ImageTk

from ceneged.comum.texto import chave_nome

# ---------------------------------------------------------------------------
#  Interface - identidade visual Ceneged
# ---------------------------------------------------------------------------

AZUL = "#014FA0"
AZUL_ESC = "#003B7A"
AZUL_MENU = "#01458C"
AZUL_CLARO = "#E7EFFA"
AZUL_SEL = "#CFE0F5"
VERMELHO = "#E31C24"
VERM_ESC = "#BB1B21"
VERM_CLARO = "#FDECEC"
FUNDO = "#F3F5F9"
BRANCO = "#FFFFFF"
TEXTO = "#1F2937"
CINZA = "#6B7280"
BORDA = "#D6DDE8"
VERDE = "#1E8E3E"
LARANJA = "#B45309"
FONTE = "Segoe UI"

_LOGO_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAEoAAAA+CAIAAAADARrxAAAbDklEQVR42sVaZ5hdVdVea+9Tbi9TMz2T3nsxJISaxBBqAFGqCkj5"
    "EFEQERAQlU+D8ggqggYUIgh8ICBgSCCUJEAKqSSZ1JkkUzLtzr13bjtt7/X9OHcmwySQUNTznF/3nrLfvdZe633ffZCI4N9xSAlS"
    "gsIBMP8DALW0Ovsa7D17RH09NTZTW7tIJCiTBdNEKQiQFJV7PBAKsqIoVlUpo0aqUydqEyYgYwAAQgDnn2kU+CXDIwIpewdBAE7D"
    "fnvDJnvdemfbdjjQJONdwjSZBGCInANjwBgg9swC5edFSJICANHvYyOGaQvP8V3yDR4KgpTgQv0y4REB4rHDReQCIwB7y0fm8jft"
    "t1eKHTtlVxeQZLoGmg6K0gOGoPfVfcfgvqjndSgl5XIyZ7DhQ/333eP76rzPFMMvI3pSAoA7qU5LS+6VpdY/XxGbNkMqB7qKXg9w"
    "JY/BPREBERDyETs8b3gYau/FAMAYMkbZrLDtwK/vC3z7m8cfw2PBIwJEq61NiUaZqvaPYR9g1qYtuSVP2f9aJptbUVfR5yPOQBKQ"
    "BEBABIZAAFKC44DtkOOAlEASPvZ+AmTAGHAOmoqaBoggBAAAZyhIpFLB55/ynX4qCAmcfWF4UgJjqXdXgWUF55wGjgOK0m+NWWvX"
    "Zx5+VLzxDmXS4PejrpG7fhDzc2zbZJhgW4QIfi+LFLDiIiwthqJCHgljIIiaBgxRCJnNiVQKYl3U1i6aWqilBRyBoRCABALgHDJZ"
    "HDqk8M3X0Ovpm8OfdCjHgo8A4Bk57NDlV3nHjVFKS8ERhIicAedm3c7u3zwkX1mKZo6FQlgQJSHIcYBz4BwMk3JZQoTiYnXCWD5x"
    "kjJ2tDpiCK+oYAVRZMdYPyIetzdvyT39rP3Sq6jrwBgIAQG/2L4j9/Y7vgXzj2cRHgc8IdSSUm3YkOb555a9+oJWXo4ATjrd+cBD"
    "mcVPKMmEGg0rPp0cAUIAZ2A7lEgSABtYrc6aoZ96kjptmlJZ0X+e83kL0C97ENyw82iUn3Ky55ST0zOmZ2+7Cz2ennyT1vvv+xbM"
    "B/pSSouUgGi1tDRNnqUUhAsf/b0NrOmWH8H2HZ5IhCkqF0JFUrjKTFOm0xCJqCfP1heeq508U4lED68qIQAA3bpyHHmVz39EYix2"
    "2nzauh18XkCkREI9/9zoY48cT4FRjj0DjIGQWkVF5N47u79/a+cl304LxzQyalGB5UhFOKiojmXKRKdWUe658grPJd/QRgzryTBB"
    "AMgYIOJn7Mg9BRZlKi1jXUxRyK26RKDr/dvJ54cHAAxBysh3ruxe8hTt3hv0ejxqMG0LGxElUWdMKS2KXHNV6KpvqeVlh3sgY8A5"
    "fu5+07O0un/2v7j/IETCIAQgkiQ+dPBRsvpzwiMAScBZ6933Grv3qh4vSVCBhRU0hLA0LfKtS0u+e51n6ND8mHoL5ucHJgEBOBc5"
    "o/v2u+y/PMnCoXxuCwF+vz7n9PykHzMuxzeLrP0Xv0z/+iGua7Z0pBQSGSL3OiJcXlp2x60uNnKc41pUn7LSelocMJZ7Z2X8jLPt"
    "x5/ASJgkAQCoikwklflz9DGjjrOzH6u0OA4oSvzRxYkf3MqLix0hbZLAOTdMRsQDAchmKegLXvmt0BWXq2Wl/asiYL4SHhVPnp0A"
    "sMMBJ5LmqveNxX81X1+GBCwQyM8a55DLUTgcfeMVpboa3eT/QvCEAM7Ty1d0Xny54vMQMEkkuGInk8qEsVxRnA/WKyUlZOVkKqlU"
    "VHvnnOZbMM8zZbJSUPCZiV026+yoM95ZZS17Q27+CBwbQ0EAzBMjRYFslhQl/Pcn9dkzSUr8oqRMSmDM2LPn0LyzeS7LNA2kJEUR"
    "6QzV1FS89gLz+1tv+EH2hZeVcJh7dMxlRTaDjPPycnXUSH3sGGXEMLWqipUUYijIPV5UVLdEkW1Jw6JUN3V0Oo0tYu9uuWO3XbeT"
    "GhtlOoe6yvx+6uVijCFjsiuOleXBxQ97ZnwFhANcob5c9TPDIwIiYZpNZy2Um7axkA8dBxlnliGD4eLX/pEvJACdix9P/GIRxpM8"
    "GkGO6AgwTTJMcmzGGOo683nR7+deD6o6YwiOQ7ZAw6RshnJZMCyQArkCug66hpznCZ3bkBiDTFaYOfXMM0KLfqFWVPRlKlISATD2"
    "aWv96PBICOS8+Sf3pB74nV5SQo7DERkQmUbR/z3jmz2ThIOMu8vG2LO7895fZv+1VEHGAgFERCJAYERAkgmJUpKUSJIRADHGOXJO"
    "mC8hSEiuzHNH4hZeAshmpWnw0SN9N93gvehCt6IiZwDgCAkMleOoYUeDJwRw3v3eBwfOPl8L+FECA2CKgrGu0C/vKbz+OnBsUNT+"
    "3WnZ8vjv/ui8txaJWCDAFIYIICUSuUyLAyICACIBA6S+eg97JIUksCzK5ogzPna05/KLvd/4Gvf5gcgVE5KIIW5u7L7h0bW1xb7T"
    "xg+4dHatwtgn5eqR8AgkSSF2zT/H3rRJ8fu5JMYVTKX1U2dXPP80yysRPFIWEUBq2Rvpvz2TW70aYl1MURVdR00lRERgQECACIyQ"
    "9RZVVyLZNliWtGxUOVaWqzNn6eedpZ8ym6laPw9CSOIMX9t86MxbXwXOQIrvn174wA/Pd2Efu62TkMh55zPPptas8RQVSccGABAO"
    "+j1FP7+Lucqt30z1GCHIeWjenNC8OUZ9Q3bF28a77zrbd4q2dsjmUNoCEAEYgEREApSELq3xelhRIa8dqE2aoJ1wgjZ1Io9GD6eG"
    "q/0+fmicM4+i66qRc15dVbfoRkPRPUd1FPrBI2RMmNahP/6ZeT0kpQRArtixruh1V3tHjCThIP8EouMOQghA9Ayq9Qyqhau/7XQn"
    "7YYDdsN+2dQiuuKQSpNtMsZQ97BQiBcX8rIBrLpCqaxi0Sj2ZS1AfYERAQG55QQAPF5OCrdshxTFtDCZzkZUHYjYEXVGOTJ08RUr"
    "sls/0iJhISUiAyEwEope/W0gQjxWt3EH5NYJRCUUVsaP844fd7ysxc2FI2Q4opvKwBQEgIDOSebNC8fMBTTgLJ9TLn7Ww9eUI8Vr"
    "2wsvEZEERALO0Umlg/Pm+IYNO/5mephPEAEREQFRzwj7UNledeeenyApCCCRc+JpK206XRk7mTY3HUhwhiQJpBOoGvrXDzoHFGbL"
    "o74hpcGoX/2E6BEhY1Yi0b12PfP5pSAkQEBhO6E5c4GASCJ8Rq6MmK+Xn8+jImKIK/d0XvnAe7HunGFL0xJk2QDEdZUAkGF9Srn2"
    "d2uBAVOV4eXh6SOL5k4oO396pcbwY/BIEnLM1O0y2to0n59JhxFIIcDn900eDwjHzswv+yACQBCm2FffyfwaIjKFk6qQEEI47rw5"
    "hgGZFJAjgeraGg/u8y99E3edXn3TxbPDoVDf6EkAltm7Rxg58vklIXAky1aiUa2iIi+0/7MHZ0hEJ48umT+rdum/PgKdgGyGIhQI"
    "WL6oZctwQCvJ7L1s3vBhg8uKowG/Vw8EfLYjGILP5wGk/mXQaOuQBBIlAAEhSKkGfNzvh//agQzhyRunP1acDehsYHVxWWGAeYJn"
    "37+uNZ7xCOOy00fefv3C45Wz0rEJUCICEgIhggAgt6b9V8AhAFFR2Peja8/sW2wKgpu70iZm2yaPHuUISW5b71O+3OLZfznxQFCA"
    "IAIi5gAR53ayW6S6/zvgiPLyH9A81Bp/6rlsU4sQgoimDA1xEGSkqwcUKJwpnHHOOGOMoXseodYRAcBbO1Aqisj7piRVbsVi2T17"
    "geg/GsNeYJyTbWd+93Dqltu9Y4b7KssZIkO8aHpZTbHHy6i6ogQ+buV/ghnBEADCE8YphQXScQhBEkhkjm22v7YM/jN1xUUlpAtM"
    "GmZm8V86Z8w2P9wc/e0iz/jxvb132ojSkydUKori9WrH5bUgMpLSX1ERnj7NSqeJc4lIQvJgqPWF543WQ8jYvyuAvUaL29w5sw+1"
    "pn7zYMf4qanfPui/48cFT/yJFxdBDzZJEA6E5k4unziiiCR+ir/zMcXgyry2las+OHuhJxRiRAjAGBPJeOkF549f/CdyBHL2pUWy"
    "l4j1KlTDtD5YYzz3gvWPl0AI7003+m+5kXm8+R2Lnve67Lk7Z+7c2zh5VC3/ZAe1vyByo//hdTc0PrnEU1rKbJsTImcUTw68/ZYh"
    "t/2odxa+ECQC6DNN0jStjVutN5fbr78l1m8Aj6Z98xL/D29Wqyo/fVOWgPBTTYkj9B4REFndyVXnLExv3uopLETLZsgYQyeRrPzO"
    "VcPuvUvxevOmOiL2mdRP9sLy/nLfURKAaGuzN2wy310t1qwR23dBLIbFRdqFC73Xf0cbPQoASDjA+BehE0dR624AM02NH1x0cWrr"
    "Nk9hIZeERByZ6EoEJ42vveWm4jPOYArvq2j7Pgd7WfIR5NhpaXHqdjkffmit30Q7d0Frm0xlAIjVVGvnnum54hJt9Oh8giA7HqP2"
    "81hJLkIz1rXxe9879NKrHp9P9ftRSIZMZtLkOOEJ40oWLAifdGJg2BA1Ejl68IQjurudtk774EF7915n5y5n9y52oAniCbQsJiUR"
    "MJ+Oo0Zp55yln3+u5qaiFABf2Oc+phHYW4IblizZ8+sHc/X1mterer2MKQBCptM8Z3KvXx9Q6q0s10pLlEiE6zqTQpoWpdIy0UVd"
    "cYolMNENuRwKhzPkHFVCkA5ylVVWKrO+4jnnLP3EWVzXeyL2pQE7Dhu3x7oyE4kDf3v60HMvZOrq0DAURec+r6IrjBBtBywbHZNL"
    "cvUPR+AMGDKucIUpSICOAOEwIub3KQNrfNMme047VZ8xTSkodDMWXdPh39Baj6icPbK/V6j11klp27G16zpWvN29Zl22fp+Mx8kw"
    "OQFnnDNkAEjIEACIETEizrji9arRsFZRoY8c6Z003jNpgjpsuKJrh60UV/t+2cCkJFcrHoYnJLkapI/lQQzRJbUkZd9mYLS1ZRsa"
    "cgcareZmp6tLpDNgWIwkqirze7VIRC0q1svL9MpKtaKMFxWxjxuNvZt+/3ZG7sKTklwamspZnUlTkCwOecN+rV+uuqzl8zQ9N1Cf"
    "UFG/zLgRMcSHXvmorr7rygWjFTchGcMVW5ofea1u/d5YR8oigEK/Nm9i+f9+c2pR2OP6kwQokQEASnJDmt/fwcOPJgLMs1fM53eP"
    "j0IAJIkIkAiPZkq6twNAPmU+4wXuv5KIcXxtfcvy13e9tOGQ4hqjNz+25oHnPwIHwJGgMEBs6so9tq29tdt45SenE7kbmMh7eYYk"
    "ROx1ltyH8I/tQFK/POcMsc8vvfmSt7cQGB5mIP1ul0QuqqNe4D7K/ZcDCkkBr6oU+WNpQ+EM73lq4wNLtmBI9wWUy06pPXFMmUfl"
    "Da3dr649+PqHze0JozTidfN2V1Mya4qaYl9NaaiX+0kiztAScufBeDxtRYP6mIFRzrDXOXYvkAB1B7pi3UY05B1bE2U9F/TiPNCR"
    "buxII+LwinBRyNMv3wCgoT3V1JHRVT66JuzXtd63u7fvaIx3xo3K0sCg0qAgchzpQUXZuC9233NbeVAvDGov33X6V4aX9D735vPG"
    "/vWt3bYjJMmfP7Pl8WW7D3RmQMigX50/ufK3184oi/rcWfzLit2Lntu6rz1tW7aqaaMqQj+7fNJZ02okERAwhs+/33Df37dsa0za"
    "hqN4+LRBBYuumjpzVJl7+4f7Ou96Yv3qnbFU1gRkxQHtmgXD7714MmE+FXc0xm9bvO6duvZU2gTOa4sCN18w+n8WjBKCOMdVdW0/"
    "+tPajQeSpmH6deXey6eoPP/JGrcGLdi4K0ZC/vF7MxZMqTZt6X58ICUg4sRBhSGfevkDKx96emsy66g+NejVu1PW9p0db+5qv3j2"
    "IK+m/OFf26/51budGVvaEhRFGk5b0vz7ivopI4qGV0QQ8c/Ld11+37utHTmpYCTkzRp2Y0v6mfcOzJ1UXlnkf2dby5wfv17XELdy"
    "DmgKOJS15cr3D2aYnDexkgC2H4yffOvSzXWdliPCEb8joSue+dfqA6GoPnNk6fq9baff9npDc0o4IhjypnPO8nUHW1KWQQAAPFl9"
    "RjJpDRjgf/jaGQpjCmduHjOGbqt4ZnX93Y9tAJ967ok1z/7wpBvPGhmNaO83xFv2JwYNjIyqCs+9e7kAFg6qD14/486vTygv8q3Z"
    "3Skkbdnf9T8LRuxvT5/90zdsiSMGRZ65dfYdF46dOap09e6OeFsmZtrnzaiZ+5M32mOm6uU3f23Mb66cPmtM8eodbRbja3Z3XHxS"
    "bWHQc8Ev39q5LxaI+h68bvpvrpx60ayaHc3J5o7s+oau6xYM++4ja3fsjat+9edXTHrkuhPOm1WzeX98f3OGaxxIKh1xkwjKo76A"
    "RzvSa2aIi5fvZgTVA/wv3n6a+/vdX5/0xIp9B2PZLfWxoWXBTMIEYNcsGPmdeSMAYPrQ4s37Y6+sbKxr7m7uyr64piGbMHlA/dvN"
    "J04eUgwA1SXBV9Y3/q0hfqA9+/K6A/VNSQS47LShi745HQC+Mqy4JW7csfhDkLS5PoaIq7a1IuJN5426dv5IAKgpDtxy/uiFG1sy"
    "pnh1XePGvQmUtGBa+Y8vnAAA1SWBJ24+cdqNr9okGYDiVi3LEf32kIiAIXbnrB2NCckwFNCXbmjK2U7OsN/f2R7rNoUkVWFdKQsJ"
    "iNHEQQVCkmEJj8YnDin55zsHQLD2eG7DvjgCeL3ajqZkcyybs5zdLd1vbW2VqkIAm+u7kJAYfG1mrZBkOULlbPLgIuCItkjlnA17"
    "OyDnoEe1hfPPdQcNS3Qkc0veqWe6SlI2tGW6MjYhfXVipZTkSMkZG1dTOLw2snV3p+LhSjSk5Qz7YEemo9soDnryBRqAgIAwkbFS"
    "OQFedeverjNueNnddQRA8OvFFYGr5w7b0hCnHrHjkmaXoLl81RYy1p0lzgxTXH7ncpAERCABfCrT2E3njqhvSoF0gCmOJM5QSlA0"
    "1t6dczkUIsRTNghUvOqv/rIJTAcQQBBoCih42fwxo6qCVtYAxjSVIyLroVgDwt6tAoBAmTW6+NnWdHfcfPqdfd8/Z4ztSJn/apRU"
    "BcsKfF4NMykxoMR3wdkjsqatcB4N6EMHBL86paqiwPfejo5PlMtECmcBr46SGIMrLhyjcgSgkM9TWeA/aeyASYML/7C0zt0ff/jV"
    "XV+dVOn3KBnDfvTVOlQ5WZIAA14FGAjLmTNr4KCygGWLgFctDXsnDSqcP7Xqra3NgABEO5vjiCAkAUOFYc4RgMAQlJvPHvv8yoOg"
    "wt1PbRxWEV4wpaqXrxm2eOmD/SVRPdZp2oZz68KxVUWBvuPPWY6qKEeacPnuS1JX+cxRpc+/vtcxnNPHl1168tC+l3WlzfNn1Ny1"
    "ZGNXwly6oXnWbUvH10Y+2N65dWebFvFaGSuVtc6cVgUehWxZHNEeuX5m39szhj2iKhIJe7uT5rPv7r/9wolhnwYAiYxZ1xBnnBVH"
    "vfxPDy1ijFasOuioyrOr6zfVdzZ1ZDc3xJ5dVX/zn9c+/37jLy6b9I9V+3M2Pbd6v6ZySXSwI7Xio0M3PLR6/JDCrGW/+G49cnbB"
    "ibVjqqOOJIWzt7a1rN7cgqpy2amDTx1X/uiKPYYhlm5o7jZsVeFt8eyGvZ33PLlh8/7Y+SfUjqkJv76uKZeymg4mNmxoaYvnTpha"
    "Ges2rKwzeWTx+SfUfrCrbe/+xEdNqc31sYCHJzL2joPxx5bvvP+lbTcsGN0az6zZ1JIStHr7ocpiX3vCuOWxtVv3d0lLXjF3uCIk"
    "3XnRREfQL/6+2cmJl97Y99LyfYAEDoAtrv/WpEtPGlp3MHnfE5uaW7q/+9vV4OFABEkTND6wJNDZbYqcA5y5XcQ9CgO6yDiALGOI"
    "goC+5Aezv37fW9mUef+TG+5/biswBoYDsdzi++cRwYIpNev/cO5Tb+7d1pRgAAumVo4eWDDtB68hAyGBAB67cdYZsWUf1XW+/HbD"
    "y6saQFPAFnCo+8wLxwLAvRdP+nB3x3sbWlZtbpu7dRkggC3AoTGjSu/82lj+05/eI4lOGVd+xtQqxpilIPMpkahv3JCCH146/q6L"
    "JghHzJlUNaY22hJLdwsSQvi9+pja8IM3zZo+rLSi0Je07ES3cc7sQUNLAyAlY2zEgGBLzs5mjYtPGVRRFBheET5jamUsYyaYapi2"
    "rvGaYs/3Lhl/w5mjkWF7MldVGDhpbNmFM2svmFk7rrZw2camF1fuB4TL5w6ZPLgo5NO+fvIQh1F72swRMs6Kw96z5gz93TVfCXg0"
    "j8a/NnuQhdQSzxqCFE2tLvVfdPLgx39wYmnElxdEvQxVEiUypsJYyHcU97c5aRnIfQzLAgwA4ls+io4fCwASAPpQ5F7jCAFyLS2O"
    "5QQHVgM4+9btEIOGqSQqiv1azwVX/n4VWfKS04ZWFvmJYM3O1h//dUN7wvR51B2PnFtVFHCEVDgDgIxpN8eyCFgY0gsCel/PEwBS"
    "hn0oluGcl0W9Pj2vhJTenTT3Ix/OsCDgAYDWN96yM9nimdMbn362YuE5VioTX7+h5sw5iffXeocPrX/j3cLTT4utW6dEgh1vra6Y"
    "P0cfUNq6bLnR1Fx12SUHHl8SGDHcM6AwsWkb93mR8YZHH/MNrlVAVAYVraQktnpLuuFAwYkzQwOryyPen//6vb+8Xe/zcklgpG0A"
    "AMO59+qpVUUBR0qFMyKQkvy6Oqw83Eey5I1IVwcFPWqwItJHiAP2Veu9DhIgJnfUbfv+LYGRI6Vj+0oGZLraoD2BwSCR9A0aaLbH"
    "VA+XBHpJWWTq5L33LyqefVLVt6/Y9bP7goMHNb/yeuXZZ6Yb6nPNzb7awd7KMubx5PbsiZ5yUtf6jWDbTi6nRaK5Xbt4SfH4Rfcl"
    "Usa1f3z//1YdkIYDBKCxqiL/bd8Yd/38UUJS328djjRKPt1GOcr+nitAtUiEe32BoYNzyWTRaac6b66wcrZeMUDz+wKTJlEue+il"
    "l5VQxEklW154EYnpVRXSyOXq92tFRYXTpmSampjXU7bwvNYX/6kEvNIyhSSjrUNms8HBNV0r1wQnTexa+e6A6VMAIBLQn7n11Dsu"
    "6trRmLQsp7zQN3VoUcinC6J+33Fg/68Pjv71xLGcMiJAzLW0Wl0xT3UVQyQgBJbavcdfU8U0PVm3c++vFg286srIlEnCMOx4MjR6"
    "ZK7l0L4Hf199xaWRcWNja9f7a6qAq+ahQ4ERw42WZgAEQagpajhEgKrfH9+yOTRqJPd4XX7TLxz95OznPv4fMU1Y7kBZ/TcAAAAA"
    "SUVORK5CYII=")
_LOGO_G_PNG = (
    "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"
    "A0hq5IiGN99YessdQXtr6fhxbn390pt/1Dj37YqpU/L1dUtvvV2VJE0+t/h/v59bu75i6pSODetTw4fYZWXLf/zT+udfSY0Yapek"
    "AMBtaVl22+31Tz+bGjfWTiY3/enBNb/8rVValhjUf/Nj/1h+1y+tZNJKJiLVVWQ5b515jpfJ6Fgy3qun77qt7y9IDBu66bGnTDa9"
    "+a8PbnvsqfiwoU5ZGQJYmv7w0kohOxfw+k1tC1Y0vLu0YcGqxm3NOYo42iZE8Jtyl3xuxE2fH88cNoMWy8Kw8963V0eFPj4i7aFg"
    "IIwkpNv3O7s1dvg+7T1IQGYkalm0aOF1N1RMGb/4xh9sfuzxJdfdUDFo4PLb76x9+YXF37zRVjq9aPGyW+5YecuthWWL/fqW98+9"
    "KDmg56Y//2XL008WVqxufnthtqXVqSwtrF296Opri2z31f/jbdwUtLZ+cO23Njz8yOq7f5scMmTR1deum3n/4qtvrBg+lI2kFy+p"
    "f+NNFuPYOlJeHnS01b74ord16/KbbwOEtT++s/md+U51D2/r1gVfvy5M6fcui99x6SQ/l+aCp2NWpDQeLY9FSxN2PMIifjoIOnJf"
    "PXfUfV+fZpix8zUOu62OCkVtf2qhu+oRaA/FG7TPgjcAaHnnXci1e83tNUcd4bW3q1hy8Pf/t+K4o2tffD27YkXgeZGystIxwwrr"
    "tg67/dbY0CGF+sbh3/9+yaETOpYsV8rSjmX7nF6+ikriheZmAGATdCxaMv4Xd0344325dZu2PfDQgAu/OOx7/+v0qPRrm/td8Pnm"
    "+Yt8L6e1siI2EDp9ew2++muxgQP8to7eZ3/Widpr77nH7llTPfWw1g8+sJIpv7nRGF8pxSxXnTL6udtPnza2SiEU0n6+rZBvK3hZ"
    "L2HJ9Im9nrjtlN9dNU0TUqe8fQwlUvtqNUUEgLJx41bl8krpqlOmG2XnWxvFGL+hOdqnT2zwoMzmdT1OOyM1ZqSXzWTWbe4946TS"
    "SePfOuOzrctXDhs31s+5TbNnZdes61iwuNcpx6dXrwcAEY+Yl9/yY47Y0d69epw8fd09v6dkIr+tLnXEJK+lzauvW3/bL/pedHbT"
    "66/VTD85s2Hj2t/P1GWlmUVLOpYtrz7ntEVXX33kU881vPJa6yuv9j3/4uZlS5E0iIS09YyJfWZM7LN8a9vyrR1t7TkEqClLDO2X"
    "GFpdGpoBwI91Qttu9PJOGwdEYr17R4ePbHx9FiiqmTHdKq+qnHSoSsbjQ4cNuOiCtiXL02s3Vh95uDNwQGrYiGivHqo0VTZ+QnrZ"
    "8uToUf2+fEHz/IUDLr6IFHas3zTyh9+L9ujBrtn054fsyrIg7436wU3Vp5zsdqQb5rw16qZvVUybtu3v/woyuWE/uKHyuOPSK9aU"
    "TZlQeuj45jfn9b/gXLBtAOh3/nlkJ/pedH7JuLF+W6Z93dpRN98Q6903rNMKC3wQoCoVHdm7ZMLgygmDK4f2SlXEIyLCYX3wx1yf"
    "K/tzhImdHT7gPX3XGLPwxh+8OmHyOxdc6La07u5kJjA874LL0uvWdn0iB37stAKz6ydczOD4AQeGzZ7X/FEf/x+QADX5be2/cQAA"
    "AABJRU5ErkJggg==")
_ICONE_PNG = (
    "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")


def _imagem(b64):
    try:
        return ImageTk.PhotoImage(Image.open(io.BytesIO(base64.b64decode(b64))))
    except Exception:
        return None


def aplicar_tema(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(bg=FUNDO)
    st.configure(".", background=FUNDO, foreground=TEXTO, font=(FONTE, 10), bordercolor=BORDA,
                 lightcolor=FUNDO, darkcolor=BORDA, troughcolor=FUNDO, focuscolor=AZUL,
                 selectbackground=AZUL, selectforeground=BRANCO)
    st.configure("TFrame", background=FUNDO)
    st.configure("Card.TFrame", background=BRANCO, bordercolor=BORDA, relief="solid", borderwidth=1)
    st.configure("TLabel", background=FUNDO, foreground=TEXTO)
    st.configure("Card.TLabel", background=BRANCO, foreground=TEXTO)
    st.configure("CardSub.TLabel", background=BRANCO, foreground=CINZA, font=(FONTE, 9))
    st.configure("Titulo.TLabel", font=(FONTE, 17, "bold"), foreground=AZUL)
    st.configure("Sub.TLabel", foreground=CINZA, font=(FONTE, 10))
    st.configure("Status.TLabel", foreground=AZUL_ESC, font=(FONTE, 9))
    st.configure("Secao.TLabel", font=(FONTE, 10, "bold"), foreground=AZUL, background=BRANCO)
    st.configure("SecaoF.TLabel", font=(FONTE, 10, "bold"), foreground=AZUL, background=FUNDO)
    # botões
    st.configure("TButton", background=BRANCO, foreground=AZUL, bordercolor=BORDA, lightcolor=BRANCO,
                 darkcolor=BRANCO, padding=(10, 5), font=(FONTE, 9, "bold"), focusthickness=0)
    st.map("TButton", background=[("disabled", FUNDO), ("pressed", AZUL_SEL), ("active", AZUL_CLARO)],
           foreground=[("disabled", "#9AA4B2")], bordercolor=[("active", AZUL)],
           lightcolor=[("active", AZUL_CLARO)], darkcolor=[("active", AZUL_CLARO)])
    for nome, cor, escura in (("Azul", AZUL, AZUL_ESC), ("Verm", VERMELHO, VERM_ESC)):
        st.configure(f"{nome}.TButton", background=cor, foreground=BRANCO, bordercolor=cor,
                     lightcolor=cor, darkcolor=cor)
        st.map(f"{nome}.TButton", background=[("disabled", "#C3CDDB"), ("pressed", escura), ("active", escura)],
               bordercolor=[("disabled", "#C3CDDB"), ("active", escura)],
               lightcolor=[("disabled", "#C3CDDB"), ("active", escura)],
               darkcolor=[("disabled", "#C3CDDB"), ("active", escura)],
               foreground=[("disabled", "#F3F5F9"), ("active", BRANCO)])
    st.configure("Peq.TButton", padding=(6, 4))
    st.configure("TCheckbutton", background=FUNDO, foreground=TEXTO, indicatorcolor=BRANCO,
                 indicatorbackground=BRANCO)
    st.map("TCheckbutton", background=[("active", FUNDO)],
           indicatorcolor=[("selected", AZUL), ("!selected", BRANCO)])
    st.configure("Card.TCheckbutton", background=BRANCO, foreground=TEXTO, indicatorcolor=BRANCO)
    st.map("Card.TCheckbutton", background=[("active", BRANCO)],
           indicatorcolor=[("selected", AZUL), ("!selected", BRANCO)])
    st.configure("TCombobox", fieldbackground=BRANCO, background=BRANCO, arrowcolor=AZUL,
                 bordercolor=BORDA, lightcolor=BRANCO, darkcolor=BRANCO, padding=3)
    st.map("TCombobox", fieldbackground=[("readonly", BRANCO)], bordercolor=[("focus", AZUL)],
           selectbackground=[("readonly", BRANCO)], selectforeground=[("readonly", TEXTO)])
    st.configure("TEntry", fieldbackground=BRANCO, bordercolor=BORDA, lightcolor=BRANCO, padding=4)
    st.map("TEntry", bordercolor=[("focus", AZUL)])
    st.configure("TSpinbox", fieldbackground=BRANCO, bordercolor=BORDA, arrowcolor=AZUL, padding=3)
    # tabelas
    st.configure("Treeview", background=BRANCO, fieldbackground=BRANCO, foreground=TEXTO, rowheight=25,
                 bordercolor=BORDA, lightcolor=BRANCO, darkcolor=BRANCO, font=(FONTE, 10))
    st.map("Treeview", background=[("selected", AZUL_SEL)], foreground=[("selected", AZUL_ESC)])
    st.configure("Treeview.Heading", background=AZUL, foreground=BRANCO, font=(FONTE, 9, "bold"),
                 relief="flat", bordercolor=AZUL_ESC, lightcolor=AZUL, darkcolor=AZUL, padding=(6, 5))
    st.map("Treeview.Heading", background=[("active", AZUL_ESC)])
    for o in ("Vertical", "Horizontal"):
        st.configure(f"{o}.TScrollbar", background="#C3CFE2", troughcolor=FUNDO, bordercolor=FUNDO,
                     arrowcolor=AZUL, lightcolor="#C3CFE2", darkcolor="#C3CFE2", gripcount=0)
        st.map(f"{o}.TScrollbar", background=[("active", AZUL)], arrowcolor=[("active", BRANCO)])
    st.configure("TPanedwindow", background=FUNDO)
    try:
        st.configure("Sash", sashthickness=6, gripcount=0, background=FUNDO)
    except tk.TclError:
        pass
    st.configure("TSeparator", background=BORDA)
    st.configure("TNotebook", background=FUNDO, borderwidth=0, tabmargins=(0, 4, 0, 0))
    st.configure("TNotebook.Tab", background="#E3E8F0", foreground=CINZA, padding=(14, 6), font=(FONTE, 10),
                 bordercolor=BORDA, lightcolor="#E3E8F0")
    st.map("TNotebook.Tab", background=[("selected", BRANCO)], foreground=[("selected", AZUL)],
           lightcolor=[("selected", VERMELHO)], font=[("selected", (FONTE, 10, "bold"))])
    root.option_add("*TCombobox*Listbox.font", (FONTE, 10))
    root.option_add("*TCombobox*Listbox.selectBackground", AZUL)
    root.option_add("*TCombobox*Listbox.selectForeground", BRANCO)


def desenhar_icone(cv, tipo, cor, t=22):
    """Ícones desenhados (não dependem de fonte com símbolos)."""
    cv.delete("all")
    m = t / 22
    L = lambda *p: [v * m for v in p]
    if tipo == "menu":
        for y in (6, 11, 16):
            cv.create_line(*L(3, y, 19, y), fill=cor, width=2.4 * m, capstyle="round")
    elif tipo == "inicio":
        cv.create_polygon(*L(11, 3, 2, 11, 5, 11, 5, 19, 17, 19, 17, 11, 20, 11), fill="", outline=cor,
                          width=2 * m, joinstyle="round")
        cv.create_rectangle(*L(9, 13, 13, 19), fill=cor, outline=cor)
    elif tipo == "cadastro":
        cv.create_rectangle(*L(3, 3, 19, 19), outline=cor, width=2 * m)
        for y in (8, 12, 16):
            cv.create_line(*L(6, y, 8, y), fill=cor, width=2 * m)
            cv.create_line(*L(10, y, 16, y), fill=cor, width=2 * m)
    elif tipo == "usuarios":
        cv.create_oval(*L(7, 2, 15, 10), outline=cor, width=2 * m)
        cv.create_arc(*L(3, 12, 19, 28), start=0, extent=180, style="arc", outline=cor, width=2 * m)
    elif tipo == "senha":
        cv.create_rectangle(*L(4, 10, 18, 20), outline=cor, width=2 * m)
        cv.create_arc(*L(7, 3, 15, 15), start=0, extent=180, style="arc", outline=cor, width=2 * m)
        cv.create_line(*L(11, 13, 11, 17), fill=cor, width=2 * m)
    elif tipo == "sair":
        cv.create_line(*L(9, 4, 4, 4, 4, 18, 9, 18), fill=cor, width=2 * m)
        cv.create_line(*L(9, 11, 19, 11), fill=cor, width=2 * m)
        cv.create_line(*L(15, 7, 19, 11, 15, 15), fill=cor, width=2 * m)
    elif tipo == "constantes":
        cv.create_line(*L(3, 19, 19, 19), fill=cor, width=2 * m)
        cv.create_line(*L(11, 4, 11, 19), fill=cor, width=2 * m)
        cv.create_line(*L(4, 7, 18, 7), fill=cor, width=2 * m)
        cv.create_line(*L(4, 7, 2, 13, 6, 13, 4, 7), fill=cor, width=1.6 * m)
        cv.create_line(*L(18, 7, 16, 13, 20, 13, 18, 7), fill=cor, width=1.6 * m)
    elif tipo == "equipes":
        cv.create_oval(*L(3, 4, 10, 11), outline=cor, width=2 * m)
        cv.create_oval(*L(12, 4, 19, 11), outline=cor, width=2 * m)
        cv.create_arc(*L(1, 13, 12, 25), start=0, extent=180, style="arc", outline=cor, width=2 * m)
        cv.create_arc(*L(10, 13, 21, 25), start=0, extent=180, style="arc", outline=cor, width=2 * m)
    elif tipo == "carteira":
        cv.create_rectangle(*L(4, 4, 18, 20), outline=cor, width=2 * m)
        cv.create_rectangle(*L(8, 2, 14, 6), fill=cor, outline=cor)
        for y in (10, 14, 17):
            cv.create_line(*L(7, y, 15, y), fill=cor, width=1.6 * m)
    elif tipo == "extras":
        cv.create_oval(*L(2, 2, 20, 20), outline=cor, width=2 * m)
        cv.create_line(*L(11, 6, 11, 16), fill=cor, width=2.4 * m)
        cv.create_line(*L(6, 11, 16, 11), fill=cor, width=2.4 * m)


def secao(pai, texto, bg=BRANCO):
    """Título de seção com o traço vermelho da marca."""
    f = tk.Frame(pai, bg=bg)
    tk.Frame(f, bg=VERMELHO, width=4, height=18).pack(side="left", padx=(0, 8))
    lbl = tk.Label(f, text=texto, bg=bg, fg=AZUL, font=(FONTE, 10, "bold"))
    lbl.pack(side="left")
    f.rotulo = lbl
    return f


def amostra(pai, cor, texto):
    """Quadradinho de cor + texto (legenda)."""
    tk.Frame(pai, bg=cor, width=10, height=10).pack(side="left", padx=(0, 4))
    tk.Label(pai, text=texto, fg=CINZA, bg=pai["bg"], font=(FONTE, 8)).pack(side="left", padx=(0, 12))


def cartao(pai, **kw):
    """Quadro branco com borda fina."""
    return tk.Frame(pai, bg=BRANCO, highlightbackground=BORDA, highlightthickness=1, **kw)


def tabela(pai, cols, altura=None, bg=BRANCO):
    f = tk.Frame(pai, bg=bg)
    t = ttk.Treeview(f, columns=[c[0] for c in cols], show="headings", height=altura or 10)
    for c, titulo, w in cols:
        t.heading(c, text=titulo, anchor="w" if w > 150 else "center")
        t.column(c, width=w, stretch=(w > 150), anchor="w" if w > 150 else "center")
    sb = ttk.Scrollbar(f, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    t.quadro = f
    return t


def dica_na_tabela(tree, texto_de, largura=520):
    """Balão de dica: passando o mouse numa linha da tabela aparece o texto completo.
    texto_de(iid) -> texto (ou None/"" = sem dica)."""
    estado = {"iid": None, "jan": None, "agenda": None}

    def esconder():
        if estado["agenda"]:
            try:
                tree.after_cancel(estado["agenda"])
            except Exception:
                pass
            estado["agenda"] = None
        if estado["jan"] is not None:
            try:
                estado["jan"].destroy()
            except Exception:
                pass
            estado["jan"] = None

    def mostrar(iid, x, y):
        estado["agenda"] = None
        try:
            txt = texto_de(iid)
        except Exception:
            txt = None
        if not txt:
            return
        j = tk.Toplevel(tree)
        j.wm_overrideredirect(True)
        try:
            j.attributes("-topmost", True)
        except Exception:
            pass
        quadro = tk.Frame(j, bg="#7A5600", padx=1, pady=1)
        quadro.pack()
        tk.Label(quadro, text=txt, bg="#FFFBEA", fg=TEXTO, font=(FONTE, 9), justify="left", anchor="w",
                 wraplength=largura, padx=8, pady=6).pack()
        j.update_idletasks()
        sw, sh = j.winfo_screenwidth(), j.winfo_screenheight()
        w, h = j.winfo_reqwidth(), j.winfo_reqheight()
        top = tree.winfo_toplevel()
        baixo = min(sh, top.winfo_rooty() + top.winfo_height())   # não passa da janela do programa
        direita = min(sw, top.winfo_rootx() + top.winfo_width())
        px = min(x + 16, direita - w - 8)
        py = y + 18 if y + 18 + h < baixo else y - h - 10
        j.wm_geometry(f"+{max(px, 0)}+{max(py, 0)}")
        estado["jan"] = j

    def mover(e):
        iid = tree.identify_row(e.y)
        if iid != estado["iid"]:
            esconder()
            estado["iid"] = iid
            if iid:
                estado["agenda"] = tree.after(450, lambda: mostrar(iid, e.x_root, e.y_root))

    def sair(_=None):
        estado["iid"] = None
        esconder()
    tree.bind("<Motion>", mover, add="+")
    tree.bind("<Leave>", sair, add="+")
    tree.bind("<ButtonPress>", sair, add="+")
    tree.bind("<MouseWheel>", sair, add="+")


def filtrar_combo(cb, todos):
    """Combobox digitável que mostra só os nomes que contêm o que foi digitado."""
    def ao_digitar(e):
        if e.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        k = chave_nome(cb.get())
        vals = todos() if not k else [m for m in todos() if k in chave_nome(m)]
        cb.configure(values=vals[:300])
    cb.bind("<KeyRelease>", ao_digitar)
    cb.configure(postcommand=lambda: None if cb.get() else cb.configure(values=todos()[:300]))
