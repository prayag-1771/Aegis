from aegis_counterfeit.data import download_kaggle, prepare_real_dataset
print("Downloading Kaggle dataset using kagglehub...")
download_kaggle()
print("Preparing real dataset...")
prepare_real_dataset()
print("Done. You can now retrain with --data data/real")
