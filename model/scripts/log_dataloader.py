from torch.utils.data import Dataset, DataLoader

class HTTPLogsDataset(Dataset):
    def __init__(self, csv_file, max_length=128):
        self.df = pd.read_csv(csv_file)
        self.max_length = max_length
        self.df = self.df.fillna('')
        self.df = self.df.astype(str)
        self.sequences = self.df.apply(self.build_sequence, axis=1)

    def build_sequence(self, row):
        seq = (
            f"<body_bytes> {row['body_bytes_sent']} </body_bytes> "
            f"<request_method> {row['request.method']} </request_method> "
            f"<request_path> {row['request.path']} </request_path> "
            f"<request_protocol> {row['request.protocol']} </request_protocol> "
            f"<request_body> {row['request_body']} </request_body>"
        )
        return seq

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        text = self.sequences[idx]
        return text
