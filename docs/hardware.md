# Hardware: radio zukka Live-Würfel

Dieser Würfel nimmt das **Master-Signal deines Mischpults** auf und schickt es
als Live-Stream an AzuraCast. Dafür braucht er einen **Audio-Eingang
(ADC/Line-In)**.

## Eingang: ADC/Line-In

Der Raspberry Pi hat keinen analogen Line-In. Die 3,5-mm-Buchse ist nur ein
Ausgang. Für das Mischpult brauchst du eines von:

1. **USB-Audio-Interface mit Stereo-Line-In** (empfohlen, Plug-and-Play),
2. **ADC-HAT** mit Linux-/Device-Tree-Support (Hersteller-Doku prüfen),
3. ein USB-Interface, das Line-In und Line-Out kombiniert (dann kannst du
   optional mithören).

## Varianten

| Variante        | Pi          | Eingang                         | Geeignet für                                 |
| --------------- | ----------- | ------------------------------- | -------------------------------------------- |
| USB (empfohlen) | Pi 4 / Pi 5 | USB-Audio-Interface mit Line-In | stabil, kein Kernel-Gebastel                 |
| kompakt         | Pi Zero 2 W | USB-Interface (OTG-Adapter/Hub) | wenig Platz, weniger CPU-Reserven            |
| ADC-HAT         | Pi 4 / Pi 5 | I2S-ADC-HAT mit Overlay         | integrierter Aufbau, nur mit Treiber-Support |

Für Live-Encoding mit ffmpeg (MP3 192 kbps + Pegelmessung) ist ein Pi 4 oder
Pi 5 die entspannte Wahl. Ein Pi Zero 2 W schafft es meist, hat aber weniger
Reserven für USB-Audio, WLAN und Encoding gleichzeitig.

## Stückliste

| Menge    | Teil                               | Hinweis                                                         |
| -------- | ---------------------------------- | --------------------------------------------------------------- |
| 1        | Raspberry Pi 4 / 5 (oder Zero 2 W) | Pi 4: 3 A, Pi 5: 5 A, Zero 2 W: 2,5 A                           |
| 1        | USB-Audio-Interface                | **Stereo-Line-In**, class-compliant; z. B. Behringer UCA202/222 |
| 1        | USB-Kabel / OTG-Adapter            | Zero 2 W braucht micro-USB-OTG-Adapter oder Hub                 |
| 1        | Audio-Adapter                      | XLR/TRS/RCA passend zum Mischpult-Master-out                    |
| optional | DI-Box / Attenuator                | wenn der Master-out zu heiß für den Line-In ist                 |
| 7        | LEDs, 5 mm                         | warmweiß/amber, diffus                                          |
| 7        | Widerstände 220–330 Ω              | je eine LED                                                     |
| 1        | Taster 16 mm, momentary (NO)       | beleuchtet, „LIVE“-Beschriftung                                 |
| 1        | Widerstand 220–330 Ω               | für 3,3-V-Taster-LED                                            |
| –        | Jumperkabel / Litze / Lochraster   | sauber verdrillt                                                |
| 1        | Gehäuse                            | Würfel ~100–120 mm, 3D-Druck oder Holz                          |
| 1        | 5-V-Netzteil                       | offiziell/hochwertig; USB-Interface zieht mit                   |

**Nicht nötig:** Verstärker, Lautsprecher. Du hörst über dein Mischpult /
deine Monitore. Ein Line-Out des Interfaces ist nur optional zum Mithören.

## Pegel und Anschluss

Mischpult-Master-out ist je nach Gerät:

- **+4 dBu symmetrisch** (XLR/TRS) – professioneller Pegel,
- **−10 dBV unsymmetrisch** (RCA) – Consumer-Pegel.

Viele günstige USB-Interfaces (UCA202/222) erwarten **−10 dBV**. Ein
+4-dBu-Master kann dann deutlich zu heiß sein und clippen. Optionen:

- Master-out am Mischpult etwas runterregeln,
- DI-Box / Line-Attenuator (z. B. −20 dB) dazwischen,
- Interface mit Gain-/Line-Eingängen verwenden (z. B. Focusrite Scarlett),
- den Würfel-VU beobachten: bei 0 dBFS leuchten alle 7 Pips = Clipping.

Ziel: laute Passagen sollten etwa **−6 dBFS** erreichen, nicht dauerhaft
alle 7 Pips (Clipping). Bei Brummen/Störgeräuschen helfen ein USB-Interface mit
eigener Stromversorgung, ein Ground-Loop-Isolator oder ein sauberer gemeinsamer
Massepunkt.

### USB-Interface anschließen

1. Interface an den Pi stecken (Zero 2 W: OTG-Adapter/Hub).
2. Mischpult-Master-out mit dem Line-In des Interfaces verbinden.
3. `arecord -l` prüfen; die Karte heißt z. B. `Device`:

   ```
   card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
   ```

4. In `config.toml`:

   ```toml
   [input]
   device = "plughw:CARD=Device,DEV=0"
   sample_rate = 44100
   channels = 2
   ```

5. Capture-Gain prüfen (falls das Interface einen Regler/ALSA-Mixer hat):

   ```bash
   alsamixer -c 1
   ```

   `F4` für Capture; Pegel so setzen, dass es bei lauten Passagen nicht clippt.

### ADC-HAT

Ein ADC-HAT nutzt das I2S-Interface des Pi:

| I2S-Signal             | Pi-Pin | BCM    |
| ---------------------- | ------ | ------ |
| BCK (Bit Clock)        | 12     | GPIO18 |
| LRCK (Word Clock)      | 35     | GPIO19 |
| ADC-Daten → Pi (`DIN`) | 38     | GPIO20 |

Wichtig: Beim **ADC** geht der Datenausgang des ADC auf **GPIO20 (PCM_DIN)**.
GPIO21 (PCM_DOUT) bleibt in diesem Aufbau frei.

Das benötigte Overlay hängt vom HAT ab und steht in der Hersteller-Doku (nicht
blind aus dieser Anleitung raten). Danach:

```bash
arecord -l
```

Die Karte erscheint z. B. als `sndrpihifiberry`; den exakten Namen in
`[input] device` eintragen.

Ein Line-Out am HAT ist optional zum Mithören; für den Stream nicht nötig.

## Pinbelegung (Beispielkonfiguration)

Alle Nummern sind **BCM-Nummern**, nicht die physischen Header-Pins. Die
physischen Pins stehen in Klammern.

| Funktion                | BCM    | Physischer Pin | Ziel                      |
| ----------------------- | ------ | -------------- | ------------------------- |
| LIVE-Taster             | GPIO17 | 11             | gegen GND (Pin 9/14/20/…) |
| Taster-LED              | GPIO27 | 13             | 220 Ω → LED → GND         |
| Pip oben links (`tl`)   | GPIO5  | 29             | 220 Ω → LED → GND         |
| Pip oben rechts (`tr`)  | GPIO6  | 31             | 220 Ω → LED → GND         |
| Pip mitte links (`ml`)  | GPIO16 | 36             | 220 Ω → LED → GND         |
| Pip mitte (`c`)         | GPIO22 | 15             | 220 Ω → LED → GND         |
| Pip mitte rechts (`mr`) | GPIO23 | 16             | 220 Ω → LED → GND         |
| Pip unten links (`bl`)  | GPIO24 | 18             | 220 Ω → LED → GND         |
| Pip unten rechts (`br`) | GPIO25 | 22             | 220 Ω → LED → GND         |

**Nicht für LEDs verwenden:** GPIO18/19/20/21 gehören zum I2S-Interface und
sind bei einem ADC-HAT belegt. GPIO12/13 wären bei aktivem Onboard-Audio
PWM-Pins; die Beispielkonfiguration meidet sie. GPIO0/1 (HAT-ID) und GPIO2/3
(I2C bei manchen HATs) bleiben ebenfalls frei.

Wenn ein HAT aufgesteckt wird, die LED-Kabel vorher an die Unterseite des
Headers löten oder einen Stacking-Header verwenden.

### LED-Verdrahtung

Jede LED wird vom GPIO-Pin über einen Vorwiderstand nach GND geschaltet:

```
GPIO ──[ 220–330 Ω ]──|>|── GND
                       LED
```

Bei 3,3 V und 220 Ω fließen ca. 5–7 mA pro LED. Sieben Pips plus Taster-LED
bleiben deutlich unter dem, was der Pi insgesamt liefern kann; pro GPIO-Pin
trotzdem nicht mehr als ~10 mA ziehen.

### Taster

Der Taster ist ein **momentary** Schalter (kein Rastschalter) und schließt
gegen GND. `gpiozero` aktiviert den internen Pull-up; die Konfiguration nutzt
`button_active_high = false`.

```
GPIO17 ────── o  o ────── GND
```

Wenn dein Taster gegen 3V3 schaltet, setze `button_active_high = true`.
Die Entprellung übernimmt `button_bounce_time`.

### Beleuchteter Taster

- **3,3-V-LED im Taster:** GPIO27 → 220 Ω → LED → GND. Direkt anschließen.
- **5-V- oder 12-V-LED im Taster:** nicht direkt an den Pi! Über einen
  Transistor (BC547/2N2222) oder ULN2803 treiben:

```
GPIO27 ──[ 1 kΩ ]── Basis NPN
                    Emitter ── GND
                    Collector ── Taster-LED ── [ R ] ── +5 V/+12 V
```

Der Emitter muss mit dem Pi-GND verbunden sein. Bei 12 V niemals GPIO und
LED direkt verbinden.

## Eingang testen

```bash
arecord -l
arecord -D plughw:CARD=Device,DEV=0 -f cd -d 5 /tmp/input-test.wav
```

Die WAV-Datei kannst du auf den Rechner kopieren und anhören. Alternativ
direkt den Pegel messen:

```bash
ffmpeg -hide_banner -f alsa -i plughw:CARD=Device,DEV=0 -t 5 \
  -af astats -f null -
```

In der Ausgabe nach `Peak level dB` bzw. `RMS level dB` suchen. Bei
laufender Musik sollte der Peak deutlich unter 0 dBFS liegen. Wenn dauerhaft
`-inf` kommt, ist der falsche Eingang, der Kanal stumm oder das Interface
nicht geöffnet.

## Gehäuse

Ein Würfel mit ca. 110–120 mm Kantenlänge bietet Platz für Pi, USB-Interface
und Kabel. Der Deckel trägt die sieben Pips, die Front den LIVE-Taster, die
Rückseite den Line-In-Anschluss (bzw. eine Kabeldurchführung zum Interface).

Draufsicht auf den Deckel (7 Pip-Positionen):

```
●           ●        tl, tr
    ●   ●   ●        ml, c, mr
●           ●        bl, br
```

Bohrbild:

| Position | Abstand von links | Abstand von oben |
| -------- | ----------------- | ---------------- |
| `tl`     | 20 %              | 20 %             |
| `tr`     | 80 %              | 20 %             |
| `ml`     | 30 %              | 50 %             |
| `c`      | 50 %              | 50 %             |
| `mr`     | 70 %              | 50 %             |
| `bl`     | 20 %              | 80 %             |
| `br`     | 80 %              | 80 %             |

Die genauen Maße hängen vom Gehäuse ab; die Prozentwerte sind als
Orientierung für ein quadratisches Top-Panel gedacht. LEDs von innen mit
Heißkleber fixieren und die Beinchen isolieren.

Rückseite/Ausschnitte:

- Lüftungsschlitze über dem Pi,
- Ausschnitt/Durchführung für Line-In (RCA/Klinke) bzw. USB-Interface,
- Zugentlastung für Netzteil und Audio-Kabel,
- optional: USB-/Ethernet-Ports des Pi.

Bei einem Metallgehäuse die WiFi-Antenne nach außen führen oder ein
Kunststoffgehäuse verwenden.

## Zusammenbau-Checkliste

1. Pi OS installieren, Netzwerk und SSH einrichten.
2. USB-Interface/ADC anschließen und mit `arecord -l` / `ffmpeg … astats`
   testen.
3. LEDs und Taster nach Tabelle verdrahten (Pi ausgeschaltet!).
4. Widerstände prüfen, Kurzschlüsse zwischen 3V3/5V und GND ausschließen.
5. Software installieren (`sudo ./deploy/install.sh`).
6. `config.toml` (Eingang, AzuraCast-Port/Mount/Username) und
   `streamer.env` (Passwort) ausfüllen.
7. `--check` ausführen, Service neu starten und LIVE drücken.
8. In der AzuraCast-Oberfläche prüfen, dass die Quelle live ist.
9. Erst dann alles ins Gehäuse einbauen.

## Sicherheit

- Arbeite nur mit abgeschaltetem und vom Netz getrenntem Pi.
- Keine 230-V-Arbeiten im Würfel. Netzteile und Verstärker müssen fertige,
  geprüfte Module sein.
- 5 V und 12 V nicht verwechseln; der Pi verträgt am 5-V-Pin keine 12 V.
- Audio-Pegel nicht übersteuern; lieber Master runter und den VU beobachten.
- Keine Litze über scharfe Gehäusekanten führen; Kabel zugentlasten.
- Bei einem Metallgehäuse: Pi und HAT mit Abstandshaltern montieren und keine
  Leiterbahnen berühren lassen.
