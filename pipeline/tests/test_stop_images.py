"""Imaginile Perseverance de la opriri: alegerea e deterministă, iar fișierele din git sunt legate corect."""

import json

import build_layers as bl
import fetch_stop_images as fsi

SITE = bl.OUT


def img(imageid, instrument="MCZ_LEFT", filt="ZCAM_L0_RGB", el=-10.0, dim="(1648,1200)", sample="Full"):
    return {"imageid": imageid, "sol": 647, "sample_type": sample, "credit": "NASA/JPL-Caltech/ASU",
            "camera": {"instrument": instrument, "filter_name": filt},
            "extended": {"mastEl": str(el), "mastAz": "0", "dimension": dim},
            "image_files": {"large": f"https://example/{imageid}_1200.jpg"}}


def test_select_prefers_color_mastcam_looking_at_terrain():
    images = [
        img("sky", el=35.0),                       # spre cer
        img("deck", el=-60.0),                     # spre punte/roți
        img("thumb", dim="(128,128)"),             # miniatură
        img("narrow", filt="ZCAM_L6_442NM"),       # filtru îngust, nu culoare naturală
        img("nav", instrument="NAVCAM_LEFT", el=-10.0),
        img("b", el=-12.0), img("a", el=-8.0),     # egal de aproape de −10°: decide imageid
    ]
    assert fsi.select_image(images)["imageid"] == "a"
    assert fsi.select_image(list(reversed(images)))["imageid"] == "a"


def test_select_falls_back_to_navcam_then_none():
    assert fsi.select_image([img("sky", el=35.0), img("nav", instrument="NAVCAM_LEFT", filt="UNK")])["imageid"] == "nav"
    assert fsi.select_image([img("sky", el=35.0)]) is None


def test_nearest_sol():
    wps = [{"sol": 10, "lat": 18.44, "lon": 77.45}, {"sol": 20, "lat": 18.45, "lon": 77.45}]
    sol, dist = fsi.nearest_sol(18.4499, 77.45, wps)
    assert sol == 20 and dist < 10


def test_attach_stop_images(tmp_path):
    stops = tmp_path / "png" / "stops"
    stops.mkdir(parents=True)
    (stops / "a.jpg").write_bytes(b"x")
    (stops / "stops.json").write_text(json.dumps({"a": {"imageid": "ZL0"}, "b": {"imageid": "ZL1"}}), encoding="utf-8")
    out = bl.attach_stop_images([{"id": "a", "image": None}, {"id": "b", "image": None}], tmp_path)
    assert out[0]["image"] == "/static/layers/stops/a.jpg" and out[0]["image_source"]["imageid"] == "ZL0"
    assert out[1]["image"] is None  # fără fișier jpg nu se leagă


def test_committed_stop_images():
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    for t in meta["targets"]:
        assert t["image"] == f"/static/layers/stops/{t['id']}.jpg", t["id"]
        path = SITE / "png" / "stops" / f"{t['id']}.jpg"
        data = path.read_bytes()
        assert data[:2] == b"\xff\xd8" and len(data) <= fsi.MAX_BYTES  # JPEG, ≤ 300 KB
        src = t["image_source"]
        assert src["credit"].startswith("NASA/JPL-Caltech") and src["imageid"] and src["link"].startswith("https://mars.nasa.gov/")
        assert src["rover_to_target_m"] <= fsi.MAX_WAYPOINT_DIST_M
