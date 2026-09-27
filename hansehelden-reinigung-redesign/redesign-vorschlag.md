# Redesign-Vorschlag hansehelden-reinigung.de

Stand: 27.09.2026 · Basis: Live-Analyse von Start-, Leistungs- und Ortsseiten sowie Abgleich
mit dem Branding von hansehelden-gruen.de, hansehelden-care.de und hansehelden.de

## Kurzfassung

Die technische Basis ist – wie bei Grün – solide: Titles, Meta-Descriptions, Schema.org
(LocalBusiness, FAQPage, City-Liste), Sitemap, saubere URLs, Manrope als Familien-Schrift.
Das Problem liegt woanders, und es ist noch ausgeprägter als bei Grün:

1. **Null Content-Fotos auf der gesamten Website.** Die einzigen zwei Bilder der Startseite
   sind das Logo (Header + Footer). Fenster-, Gewerbe- und alle 15 Ortsseiten: ebenfalls nur
   Logo. Eine Reinigungsfirma verkauft ein sichtbares Ergebnis – die Seite zeigt buchstäblich
   keines. Zum Vergleich: Care hat inzwischen 10+ echte Fotos in mehreren Auflösungen.
2. **Die zwei stärksten Zielgruppen haben keine eigene Bühne.** Schaufensterreinigung ist
   nur ein Listenpunkt auf der Fenster-Seite (5 Erwähnungen, keine eigene Sektion).
   Treppenhausreinigung kommt auf der Gewerbe-Seite genau **einmal** vor – dabei sind
   Hausverwaltungen/WEG mit festen Turnusverträgen das planbarste Geschäft im Portfolio.
3. **15 baugleiche Ortsseiten** („Reinigung [Ort]“) mit identischem Aufbau – dasselbe
   Doorway-Page-Risiko und dieselbe Kannibalisierung, die die GSC-Daten bei Grün belegt
   haben (dort: 0 von 16 Ortsseiten mit einer einzigen Impression).

## Der Bestand im Detail

| Seite | Content-Fotos | Anmerkung |
|---|---|---|
| Startseite | 0 | Text-Hero, Emoji-Telefon-Icon, 3 Leistungskarten ohne Bild |
| /professionelle-fensterreinigung-…/ | 0 | Gute Texte (Küste/Salzluft!), Schaufenster nur als ✓-Punkt |
| /professionelle-gewerbereinigung-…/ | 0 | Treppenhaus nur als ✓-Punkt „Treppenhaus- und Fassadenreinigung“ |
| /baustellenreinigung-…/ | 0 | |
| 15 × /reinigung-[ort]/ | 0 | baugleich, kein Ortsbezug außer dem Namen |

**Was gut ist und bleibt:** die Farbwelt (Königsblau `#27407f`/`#3352a4`, Akzent Gold
`#f2c94c`), Manrope, die Pflegekassen-Verzahnung mit Care, das Schema.org-Fundament,
die Odoo-Lead-Anbindung, die Texte zur Küstenlage (Salzluft, Wetter) – das ist ein
echtes regionales Differenzierungsmerkmal und wird im Redesign zum roten Faden.

## Das Konzept: drei Zielgruppen, drei Bühnen

Ziel laut Briefing: **mehr Bilder, Fokus Fensterreinigung, Schaufenster und Aufgänge
von Mehrfamilienhäusern.** Die neue Startseite erzählt deshalb nicht mehr
„Fenster / Gewerbe / Bau“ (Innenperspektive), sondern spricht drei Kundengruppen
direkt an:

| Zielgruppe | Sektion im Mockup | Kernbotschaft |
|---|---|---|
| Privatkunden | Fensterreinigung (Karte 1 + FAQ + Pflegekasse) | Streifenfrei trotz Salzluft, auch Wintergarten/Dachfenster |
| Einzelhandel, Gastro, Praxen | „Schaufenster, die verkaufen“ | Fester Wochenturnus vor Ladenöffnung, Monatspauschale, Sammeltermine für Nachbargeschäfte |
| Hausverwaltungen, WEG, Vermieter | „Aufgänge, über die sich niemand mehr beschwert“ | Reinigungsplan mit Leistungsnachweis im Hausflur, ein Ansprechpartner, kombinierbar mit Außenanlagen (Grün) |

Gewerbe- und Baustellenreinigung bleiben als kompakte Zweitzeile erhalten, verschwinden
also nicht – sie dominieren nur nicht mehr die Erzählung.

Der klickbare Entwurf liegt unter [`mockup/index.html`](mockup/index.html)
(Vorher/Nachher-Regler, Zielgruppen-Bänder, Formular mit Checkbox-Fix von Grün,
responsiv; alle Foto-Platzhalter sind mit der Shotliste beschriftet).

**Typografie & Farbe:** Manrope bleibt, Überschriften in ExtraBold (800) mit leicht
negativem Letter-Spacing – identisch zum Grün-Redesign, damit die Familie als Familie
erkennbar wird. Königsblau bleibt Markenfarbe, Gold `#f2c94c` wird gezielt für
Bewertungssterne und die Pflegekassen-Zahl eingesetzt.

## Bildkonzept: die Shotliste

Der größte Hebel ist ein halber Tag Fotoshooting – idealerweise am selben Tag wie das
für Grün geplante Shooting (ein Fotograf, zwei Marken, halbe Kosten):

| # | Motiv | Einsatzort |
|---|---|---|
| 1 | Mitarbeiter:in mit Abzieher an großer Glasfront, Morgenlicht | Hero Startseite |
| 2 | Nahaufnahme: Hände, Abzieher, ablaufendes Wasser auf Glas | Karte Fensterreinigung |
| 3 | Schaufenster in der Greifswalder Innenstadt, früher Morgen, Team im Bild | Karte + Band Schaufenster |
| 4 | Treppenhaus Altbau: gewischte Stufen, glänzender Handlauf, Licht von oben | Karte + Band Treppenhaus |
| 5 | Vorher/Nachher-Paar einer Glasfront (exakt gleicher Standpunkt!) | Slider |
| 6 | Team-Gruppenfoto vor Firmenwagen (ggf. gemeinsam mit Grün-Team) | Über-uns / hansehelden.de |
| 7 | Wintergarten oder Dachfenster in Aktion | Fenster-Leistungsseite |
| 8 | Büro/Praxis nach der Reinigung, aufgeräumt, Gegenlicht | Gewerbe-Leistungsseite |
| 9 | Besenreine Baustelle / Übergabe | Baustellen-Leistungsseite |
| 10 | Je Top-Ort 1 Foto mit erkennbarem Ortsbezug | Ortsseiten (Top 5) |

**SEO-Doppelnutzen** (wie bei Grün): beschreibende Dateinamen
(`schaufensterreinigung-greifswald-hansehelden.jpg`), Alt-Texte mit Ortsbezug, und jedes
Foto zusätzlich ins Google-Unternehmensprofil. Echte lokale Fotos statt Stock.

## Neue Seiten & SEO

1. **Zwei neue Leistungsseiten** mit echtem Suchpotenzial:
   - `/schaufensterreinigung-greifswald/` – „Schaufensterreinigung Greifswald & Umgebung“
   - `/treppenhausreinigung-vorpommern-greifswald/` – Zielkeywords „Treppenhausreinigung
     Greifswald“, „Treppenhausreinigung Hausverwaltung“, „Unterhaltsreinigung
     Mehrfamilienhaus“. Inhalt: Leistungsverzeichnis, Umlagefähigkeit als Betriebskosten,
     Leistungsnachweis, Referenzobjekte.
2. **Ortsseiten wie bei Grün behandeln:** nicht löschen, sondern die Top-5-Orte
   (Greifswald, Wolgast, Anklam, Usedom, Grimmen) mit je zwei individuellen Abschnitten
   („Schaufensterreinigung in [Ort]“ / „Treppenhausreinigung in [Ort]“) und 2 FAQ
   aufrüsten; die übrigen 10 zunächst beobachten. Vorher unbedingt **GSC-Export ziehen**
   (für Reinigung liegt – anders als bei Grün – noch keiner vor) und die Entscheidung
   datenbasiert treffen.
3. **Lokale Signale** (identisch zum Grün-Plan): Google-Unternehmensprofil mit eigener
   Kategorie „Fensterreinigung“ + „Gebäudereinigung“, Bewertungsprozess nach jedem
   Auftrag, NAP-konsistente Brancheneinträge. Für die Hausverwaltungs-Schiene zusätzlich:
   Direktansprache der Verwaltungen in Greifswald/Wolgast mit PDF-Leistungsverzeichnis –
   dieser Vertrieb läuft über Beziehungen, nicht über Google.
4. **Formular-Checkbox-Fix** aus `hansehelden-gruen/_redesign/kontakt-checkbox.md` auch
   hier einspielen (gleiches Template, gleiches Problem) – heute machbar.

## Lohnt sich auch ein Redesign von hansehelden.de?

Kurze Antwort: **ein Facelift ja, ein komplettes Redesign nein – und erst nach dem
Reinigung-Relaunch.**

Befund: Die Dachmarken-Seite ist strukturell modern (Sticky-Nav, Karten-Layout,
responsive, klare Abläufe), hat aber dieselbe Schwäche wie Reinigung: **nur 3 Bilder,
alle drei Logos.** Die vier Marken werden mit Emojis (🌿✨💙🏠) statt Fotos oder echten
Icons präsentiert, und der Orange-Akzent `#f18200` taucht in keiner der Untermarken auf.

Einordnung: hansehelden.de ist eine Brand-Seite – sie rankt für „Hansehelden“, nicht
für „Fensterreinigung Greifswald“. Der kommerzielle Traffic läuft über die Untermarken.
Darum genügt ein halber Tag Facelift statt Relaunch:

- Die vier Markenkarten bekommen **echte Fotos** (fallen beim Shooting ohnehin ab:
  Shot 6 Team, je 1 Einsatzfoto pro Marke) und die **Markenfarbe als Kante/Akzent**
  (Grün `#6c964a`, Blau `#27407f`, Hellblau `#1e98cb`, Immobilien-Farbe).
- Emojis durch ein konsistentes Icon-Set ersetzen, Headline-Stil auf Manrope 800
  angleichen – dann sehen alle fünf Seiten nach einer Familie aus.
- Team-/Über-uns-Sektion mit dem Gruppenfoto und dem Beachcup-Sponsoring ausbauen –
  das ist die eigentliche Aufgabe einer Dachmarken-Seite (Vertrauen, Arbeitgebermarke).

## Umsetzungsfahrplan

| Phase | Inhalt | Zeitrahmen |
|---|---|---|
| **Sofort** | Checkbox-Fix einspielen · GSC-Export für Reinigung ziehen | heute |
| **Woche 1–2** | Fotoshooting nach Shotliste (gemeinsam mit Grün) · Google-Unternehmensprofil · Brancheneinträge | parallel |
| **Woche 3–5** | Startseite nach Mockup umbauen · 2 neue Leistungsseiten (Schaufenster, Treppenhaus) live | Relaunch v1 |
| **Woche 6–8** | Top-5-Ortsseiten individualisieren · Hausverwaltungs-Mailing mit Leistungsverzeichnis | Vertrieb + SEO |
| **danach** | hansehelden.de-Facelift (Fotos, Markenfarben, Icons) | ½ Tag |
