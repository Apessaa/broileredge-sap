# Bench test protocol (24–72 h, before any house installation)

**Purpose:** this test turns three "designed" rows of Table V into measured results:
- **O1:** the real sensors on a real RS-485 bus;
- **O2:** the persistence rule on continuous data;
- **O6:** the code running on the Raspberry Pi.

Every number in the paper must come from `bench_results.json` of your own run.

**If a sensor cannot arrive in time** (realistically, if it is not on the bench by about 15 November),
run the test with the devices you have, and state exactly which ones in the paper. Do not substitute
another sensor model and describe it as the planned one.

## 1. Bill of materials (quantities only; get quotes locally)

| Item | Qty | Notes from the manufacturers' documents |
|---|---|---|
| Raspberry Pi 4 Model B (≥ 2 GB) or Pi 5, official power supply, 32 GB microSD | 1 | Raspberry Pi OS (Bookworm) has Python 3.11. No extra packages are needed |
| USB–RS485 adapter with switchable 120 Ω termination | 1 | One end of the bus |
| 24 VDC power supply, ≥ 1 A | 1 | Powers the ODMHM-R units and the anemometer |
| Sentera ODMHM-R | 3 | 24 VDC over the RJ45 socket (Power over Modbus). Pins: 1 = 24 VDC, 3 = A, 5 = /B, 7 = GND. CO₂ reaches its stated accuracy only after 25 h of continuous operation |
| Seeed S-NH3-01 | 2 | Supply 4.5–5.5 VDC (5 V recommended). **Do not connect it to 24 V.** Use a 24 → 5 V DC–DC converter at each sensor. Warm-up about 5 min |
| Delta OHM / Senseca HD53LS.S | 1 | Supply 10–30 VDC. Modbus starts 10 s after power-up |
| Shielded twisted-pair RS-485 cable, RJ45 plugs, terminal blocks | — | Daisy chain only (no star). Ground the shield at one end. Use a common GND |
| 120 Ω resistor | 1 | Far end of the bus. The ODMHM-R's own resistor (holding register 9) may be used instead, but on only two devices in total |
| Reference thermohygrometer with a calibration certificate | 1 | For the bias check. A handheld NH₃ or CO₂ meter is optional |
| Desk fan | 1 | Air-speed steps |

Optional but useful: a 100 m reel of the bus cable, so the bench bus has the length of the real house.

## 2. Commissioning (one device at a time, on its own)

Record the serial number, firmware, final address and settings of every device in a commissioning
log. The bus runs at **9600 baud 8N1** because the NH₃ sensor is fixed at that setting.

1. **ODMHM-R** (factory setting: address 1, 19200 8E1, CO₂ self-calibration on):
   ```
   python3 commission.py odmhm-offset --port /dev/ttyUSB0 --baud 19200 --parity E --unit 1
   python3 commission.py odmhm-setup  --port /dev/ttyUSB0 --baud 19200 --parity E --unit 1 --new-unit 2
   ```
   `odmhm-setup` switches CO₂ self-calibration off, sets the address, 8N1 and 9600. Power-cycle the
   device, then check it with `scan` at 9600 8N1. If the device does not answer, configure it with
   Sentera's 3SModbus tool instead.
2. **HD53LS.S** (factory setting: address 1, 19200 8E1): power it on, send `@` within 10 s to enter
   configuration mode, then send `CU5A21` (address 21), `CU5B3` (9600) and `CU5M0` (8N1). Power-cycle
   it. `scan` must show `speed_unit_code = 0` (m/s). Check the command syntax against the manual
   before you send anything.
3. **S-NH3-01:** find its address (the datasheet example uses 0x0F). Set 11 and 12 with the
   address-change frame in its datasheet, with only that sensor on the bus.
4. Assemble the bus in the order of Fig. 2 (#1, #21, #2, #11, #3, #12), with termination at both ends.
5. On the Pi:
   - Run `python3 tests/test_edge.py` (the emulator tests also run on the Pi; record the pass count).
   - Run `python3 commission.py scan --config config.json`: all six devices must answer.

## 3. Logging and disturbance schedule

Copy `edge/` to the Pi, edit `config.json` (port, flock dates) and start the logger:

```
python3 edge_live.py --config config.json      # runs until stopped
```

To survive reboots, run it as a systemd service.

- **Phase A (0–25 h), side by side:** all ODMHM-R units sit next to the reference instrument, and the
  NH₃ sensors sit next to each other. CO₂ is still warming up. Read the reference every hour into
  `reference.csv` (columns `time,T,RH`; add `CO2,NH3` if you have them), or log it automatically.
- **Phase B (25–48 h):** leave everything undisturbed, with hourly reference readings.
- **Phase C (48–72 h), disturbances:** write each one into `events.csv` (`start,end,kind,unit`):
  1. Unplug one ODMHM-R for 10 min. Expected: `comm:timeout` for that unit only.
  2. Power-cycle one NH₃ sensor. Expected: `warmup` for 5 min.
  3. Breathe or blow towards one ODMHM-R for 2 min. Expected: a CO₂ step. No open flames or gas cylinders.
  4. Warm one ODMHM-R gently, for example with a hair dryer at a safe distance, so that its zone stays
     above a band for at least 15 min, then let it cool. Expected: the level rises after two windows
     and falls after three.
  5. Point the fan at the anemometer at three settings. Expected: three air-speed steps.
  6. If the middleware runs, unplug the network for 30 min. Expected: the outbox grows, then empties
     with no duplicate rows in SAP or the mock.
  7. Pull the Pi's power plug, then restart. Expected: no outbox row is lost.
  8. Create `maintenance.flag` for 10 min. Expected: every reading is flagged.

## 4. Analysis

```
python3 ../bench/bench_analysis.py logs --config config.json --reference reference.csv --events events.csv
```

`bench_results.md` reports:
- completeness and error kinds per sensor;
- spread between co-located sensors (Phase A/B only);
- bias against the reference;
- level changes per day with and without persistence, and the delay persistence adds;
- the outbox backlog;
- poll duration, lateness, CPU share and memory on the Pi.

The pipeline was smoke-tested end to end with emulated sensors (`edge/tests/test_live_smoke.py`). That
test is not a substitute for this one.

## 5. What goes into the paper (about 6 lines)

Add a subsection or extend V-C, filling in your own numbers:

> On a bench, the six sensors ran on one 9600-baud bus to a Raspberry Pi [model] for H h: x% of the
> polls were valid (errors: …), a poll took a median of y s (max z s), the program used c% CPU and m MB
> memory, and co-located transmitters differed by at most … °C and …% RH, with a bias of … against a
> calibrated reference. The persistence rule cut level changes from r to p per day at a median delay of
> one window. All injected disturbances were flagged as designed [or: except …].

Then update Table V:
- **O1:** "hardware tested on a bench (EVAL3)"
- **O6:** "met on the device"

Remove the matching phrases from the threats paragraph in Section VI.
