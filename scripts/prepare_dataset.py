from src.dataset import load_training_data
from src.preprocessing import (
    preprocess_traffic,
    preprocess_schedule,
)
from src.features.builder import FeatureBuilder


def main():
    traffic, schedule, labels = load_training_data()

    traffic = preprocess_traffic(traffic)
    schedule = preprocess_schedule(schedule)

    builder = FeatureBuilder()

    dataset = builder.build_training_dataset(
        traffic=traffic,
        schedule=schedule,
        labels=labels,
    )

    dataset.to_parquet(
        "../data/processed/train_features.parquet",
        index=False,
    )

    print(f"Prepared {len(dataset)} rows")


if __name__ == "__main__":
    main()