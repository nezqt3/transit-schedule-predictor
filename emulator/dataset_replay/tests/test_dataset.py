from pathlib import Path

from dataset_replay.app.dataset import TrafficDataset


def test_dataset_sorts_by_availability_and_filters_invalid(tmp_path: Path) -> None:
    traffic = tmp_path / "traffic.csv"
    traffic.write_text(
        "packet_id,tr_id,unit_id,event_time,location_valid,lon,lat,alt,speed,heading,receive_time\n"
        "2,10,20,2026-01-01 10:00:02,True,37.2,55.2,100,20,90,2026-01-01 10:00:03\n"
        "1,10,20,2026-01-01 10:00:01,False,,,,,,2026-01-01 10:00:01\n",
        encoding="utf-8",
    )
    dataset = TrafficDataset(traffic)
    scenario = dataset.scenarios()[0]
    assert scenario.packets == 2
    assert scenario.valid_packets == 1
    rows = dataset.select(
        [10], valid_locations_only=True, start_at=None, end_at=None,
    )
    assert len(rows) == 1
    assert rows[0].longitude == 37.2
