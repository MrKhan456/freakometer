# Put this inside a TouchDesigner DAT Execute DAT connected to your UDP In DAT.
# Make sure the UDP In DAT is listening on port 7000.
# Also create a Constant CHOP named controls.

import json


_td_op = globals().get("op")

def onTableChange(dat):
    try:
        raw = dat[-1, 0].val
        data = json.loads(raw)

        selected_stem = data.get("selectedStem", "vocals")
        volume = float(data.get("volume", 1))
        filter_value = float(data.get("filterValue", 8000))
        pitch_value = float(data.get("pitchValue", 1))
        energy = float(data.get("energy", 1))

        stem_map = {
            "vocals": 0,
            "drums": 1,
            "bass": 2,
            "other": 3
        }

        selected_index = stem_map.get(selected_stem, 0)

        c = _td_op("controls") if callable(_td_op) else None

        if c is not None:
            c.par.name0 = "selectedIndex"
            c.par.value0 = selected_index
            c.par.name1 = "volume"
            c.par.value1 = volume
            c.par.name2 = "filterValue"
            c.par.value2 = filter_value
            c.par.name3 = "pitchValue"
            c.par.value3 = pitch_value
            c.par.name4 = "energy"
            c.par.value4 = energy

    except Exception as e:
        print("UDP parse error:", e)

    return
