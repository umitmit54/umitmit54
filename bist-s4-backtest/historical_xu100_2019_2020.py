from __future__ import annotations
import pandas as pd

# Anchor: published BIST100 constituent list used in a peer-reviewed study, matching 2019 Q3.
Q3_2019 = set('''ADESE AEFES AFYON AGHOL AKBNK AKSA AKSEN ALARK ALBRK ALGYO ANACM ARCLK ASELS AVOD BERA BIMAS BJKAS CCOLA CEMAS CEMTS CLEBI DGKLB DOHOL ECILC EGEEN ENKAI EKGYO ENJSA EREGL FENER FROTO GARAN GENTS GEREL GOLTS GOZDE GSDHO GSRAY GUBRF HALKB HEKTS HURGZ ICBCT IEYHO IHLAS IHLGM INDES IPEKE ISCTR ISDMR ISFIN ISGYO ITTFH KARSN KCHOL KERVT KONYA KORDS KOZAA KOZAL KRDMD MAVI METRO MGROS MPARK NETAS NTHOL ODAS OTKAR OZGYO PARSN PETKM PGSUS POLHO PRKME SAHOL SASA SISE SKBNK SODA SOKM TAVHL TCELL THYAO TKFEN TMSN TOASO TRKCM TSKB TTKOM TTRAK TUKAS TUPRS ULKER VAKBN VERUS VESTL YATAS YKBNK ZOREN'''.split())

# Official Borsa Istanbul periodic changes.
CHANGES = {
    '2019Q2': (set('OZGYO ISFIN TSPOR IEYHO'.split()), set('ECZYT DEVA FLAP ANELE'.split())),
    '2019Q3': (set('TUKAS ADESE KONYA AVOD AGHOL'.split()), set('TATGD GOODY TSPOR KARTN GLYHO'.split())),
    '2019Q4': (set('GLYHO DOAS TRGYO HLGYO DEVA GUSGR'.split()), set('GENTS INDES HURGZ ADESE ISGYO OZGYO'.split())),
    '2020Q1': (set('ADANA AKGRT ALKIM ANHYT AYGAZ BIZIM BRISA BRSAN BTCIM BUCIM CIMSA ECZYT ERBOS GOODY INDES ISGYO ISMEN KAREL KARTN KLMSN LOGO TATGD TRCAS'.split()), set('AFYON AVOD BERA BJKAS CEMAS DGKLB FENER GEREL GLYHO GOLTS GSRAY ICBCT IEYHO IHLAS IHLGM ITTFH KONYA METRO PARSN POLHO PRKME TUKAS VERUS'.split())),
    '2020Q2': (set('AKCNS GLYHO OZKGY RYGYO SELEC'.split()), set('BTCIM ERBOS GSDHO INDES TRCAS'.split())),
    '2020Q3': (set('BAGFS DOCO GSDHO OYAKC'.split()), set('ANHYT ECZYT RYGYO SARKY'.split())),
    '2020Q4': (set('AKSGY ALCTL ARDYZ INDES PETUN PNSUT'.split()), set('ANACM GLYHO KARSN KLMSN SODA TRKCM'.split())),
}

def apply(prev: set[str], include: set[str], exclude: set[str]) -> set[str]:
    return (set(prev) - set(exclude)) | set(include)

def reverse(next_: set[str], include: set[str], exclude: set[str]) -> set[str]:
    return (set(next_) - set(include)) | set(exclude)

UNIVERSES = {}
UNIVERSES['2019Q3'] = set(Q3_2019)
UNIVERSES['2019Q2'] = reverse(UNIVERSES['2019Q3'], *CHANGES['2019Q3'])
UNIVERSES['2019Q1'] = reverse(UNIVERSES['2019Q2'], *CHANGES['2019Q2'])
UNIVERSES['2019Q4'] = apply(UNIVERSES['2019Q3'], *CHANGES['2019Q4'])
UNIVERSES['2020Q1'] = apply(UNIVERSES['2019Q4'], *CHANGES['2020Q1'])
UNIVERSES['2020Q2'] = apply(UNIVERSES['2020Q1'], *CHANGES['2020Q2'])
UNIVERSES['2020Q3'] = apply(UNIVERSES['2020Q2'], *CHANGES['2020Q3'])
UNIVERSES['2020Q4'] = apply(UNIVERSES['2020Q3'], *CHANGES['2020Q4'])

for k,v in UNIVERSES.items():
    if len(v) != 100:
        raise RuntimeError(f'{k} reconstructed universe has {len(v)} symbols, expected 100')

def quarter_key(dt) -> str:
    d = pd.Timestamp(dt)
    q = (d.month - 1)//3 + 1
    return f'{d.year}Q{q}'

def universe_for_date(dt) -> list[str]:
    k = quarter_key(dt)
    if k not in UNIVERSES:
        raise KeyError(k)
    return sorted(UNIVERSES[k])

if __name__ == '__main__':
    for k in sorted(UNIVERSES): print(k, len(UNIVERSES[k]), ','.join(sorted(UNIVERSES[k])[:5]), '...', ','.join(sorted(UNIVERSES[k])[-5:]))
