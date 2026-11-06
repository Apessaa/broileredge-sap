"""Fig. 2 of paper v24: the authors' data model with key attributes only and larger type (full attributes in the replication package)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = "DejaVu Sans"
W, H = 2000, 1580
fig = plt.figure(figsize=(W / 200, H / 200), dpi=200)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
ROW, HEAD, FS = 58, 74, 18
LW = 2.6
X = (10, 705, 1400)
EW = 590


def entity(x, y, name, keys, attrs, w=EW):
    h = HEAD + ROW * (len(keys) + len(attrs)) + 20
    ax.add_patch(Rectangle((x, y), w, h, fill=False, lw=LW, ec="#1a1a1a"))
    ax.add_patch(Rectangle((x, y), w, HEAD, fc="#e6e6e6", ec="#1a1a1a", lw=LW))
    ax.text(x + w / 2, y + HEAD / 2, name, ha="center", va="center", fontsize=FS + 1, fontweight="bold")
    yy = y + HEAD + 4
    for k, f in keys:
        ax.text(x + 18, yy + ROW / 2, k, ha="left", va="center", fontsize=FS, fontweight="bold")
        ax.text(x + 118, yy + ROW / 2, f, ha="left", va="center", fontsize=FS)
        yy += ROW
    ax.plot([x, x + w], [yy + 6, yy + 6], color="#1a1a1a", lw=2)
    yy += 10
    for a in attrs:
        ax.text(x + 40, yy + ROW / 2, a, ha="left", va="center", fontsize=FS)
        yy += ROW
    return {"x": x, "y": y, "w": w, "h": h, "cx": x + w / 2, "r": x + w, "b": y + h}


def hlink(a, b, y, l1="N", l2="1"):
    """horizontal link from the right edge of a to the left edge of b at height y"""
    ax.plot([a["r"], b["x"]], [y, y], color="#1a1a1a", lw=2.4)
    ax.text(a["r"] + 30, y - 40, l1, fontsize=FS + 1, color="#555", ha="center", va="center")
    ax.text(b["x"] - 30, y - 40, l2, fontsize=FS + 1, color="#555", ha="center", va="center")


def vlink(a, b, x, l1="1", l2="N"):
    """vertical link from the bottom of a to the top of b at x"""
    ax.plot([x, x], [a["b"], b["y"]], color="#1a1a1a", lw=2.4)
    ax.text(x + 30, a["b"] + 26, l1, fontsize=FS + 1, color="#555", ha="center", va="center")
    ax.text(x - 34, b["y"] - 28, l2, fontsize=FS + 1, color="#555", ha="center", va="center")


user = entity(X[0], 24, "User", [("PK", "UserID"), ("FK", "FarmID")], ["Name, Role"])
farm = entity(X[1], 24, "Farm", [("PK", "FarmID")], ["FarmName"])
y2 = 322
dev = entity(X[0], y2, "Device", [("PK", "DeviceID"), ("FK", "HouseID")], ["DeviceType"])
house = entity(X[1], y2, "House", [("PK", "HouseID"), ("FK", "FarmID")], ["SAPFuncLoc"])
flock = entity(X[2], y2, "Flock", [("PK", "FlockID"), ("FK", "HouseID")], ["Strain", "SampleWeight", "SAPFlockRef"])
y3 = 810
sensor = entity(X[0], y3, "Sensor", [("PK", "SensorID"), ("FK", "DeviceID")], ["Parameter, Zone"])
reading = entity(X[1], y3, "Reading", [("PK", "ReadingID"), ("FK", "SensorID")], ["Timestamp, Value"])
sa = entity(X[2], y3, "StressAssessment", [("PK", "AssessmentID"), ("FK", "FlockID"), ("FK", "Task1–Task3"),
                                           ("FK", "PossibleCause")],
            ["Inputs, levels", "Cause, RuleVersion", "SentToSAP"])
y4 = 1180
pcause = entity(X[0], y4, "PossibleCause", [("PK", "CauseCode"), ("PK", "RuleVersion")], ["Text, Sources"])
task = entity(X[1], y4, "Task", [("PK", "TaskCode"), ("PK", "RuleVersion")], ["Text, Source", "Basis (E/I)"])

# relationships (1 — N), as in the authors' diagram
hlink(user, farm, 24 + HEAD + ROW)                                   # User N - 1 Farm
vlink(farm, house, farm["cx"])                           # Farm 1 - N House
hlink(dev, house, y2 + HEAD + ROW)                              # Device N - 1 House
hlink(house, flock, y2 + HEAD + ROW, "1", "N")                  # House 1 - N Flock
vlink(dev, sensor, dev["cx"])                            # Device 1 - N Sensor
hlink(sensor, reading, y3 + HEAD + ROW, "1", "N")               # Sensor 1 - N Reading
vlink(flock, sa, flock["cx"])                            # Flock 1 - N Assessment
hlink(task, sa, y4 + HEAD + ROW, "1", "N")                      # Task 1 - N Assessment (x3)
# PossibleCause 1 - N Assessment: below Task, then up into the assessment
yb = max(pcause["b"], task["b"]) + 30
ax.plot([pcause["cx"], pcause["cx"]], [pcause["b"], yb], color="#1a1a1a", lw=2.4)
ax.plot([pcause["cx"], sa["cx"]], [yb, yb], color="#1a1a1a", lw=2.4)
ax.plot([sa["cx"], sa["cx"]], [yb, sa["b"]], color="#1a1a1a", lw=2.4)
ax.text(pcause["cx"] + 30, pcause["b"] + 22, "1", fontsize=FS + 1, color="#555", ha="center", va="center")
ax.text(sa["cx"] + 30, sa["b"] + 22, "N", fontsize=FS + 1, color="#555", ha="center", va="center")

for i, t in enumerate(["PK primary, FK foreign key", "1 — N one-to-many", "Task1–Task3: up to three",
                       "Key attributes only; full", "model in the replication", "package"]):
    ax.text(X[2] + 10, 36 + i * 44, t, fontsize=FS - 4, color="#555", ha="left", va="center")
assert yb + 10 < H, yb
fig.savefig("data_model_key_attributes.png", dpi=200, facecolor="white")
print("saved", "bottom", yb, "sa", sa, "task", task)
