import os
import json

from .paths import MODEL_ID, MODEL_REVISION, model_dir


class LocalEmbedder:
    identity = f"{MODEL_ID}@{MODEL_REVISION}:normalized:v1"

    def __init__(self):
        self._model = None

    def load(self):
        if self._model is None:
            location = model_dir()
            if not (location / "modules.json").exists():
                raise RuntimeError(
                    "Local model is missing. Rebuild the Docker image with internet access."
                )
            revision = location / "REVISION"
            if not revision.exists() or revision.read_text().strip() != MODEL_REVISION:
                raise RuntimeError("Local model revision differs from the index configuration. Rebuild the image.")
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            self._model = _MiniLM(location)
        return self._model

    def passages(self, passages):
        from .documents import Passage
        model = self.load()
        size = model.max_seq_length - model.tokenizer.num_special_tokens_to_add(pair=False)
        result = []
        for passage in passages:
            offsets = model.tokenizer(passage.text, add_special_tokens=False, truncation=False,
                                      return_offsets_mapping=True)["offset_mapping"]
            start = 0
            while start < len(offsets):
                end = min(start + size, len(offsets))
                text = passage.text[offsets[start][0]:offsets[end - 1][1]]
                # A window beginning inside a word can tokenize differently in isolation.
                while len(model.tokenizer.encode(text)) > model.max_seq_length and end > start + 1:
                    end -= 1
                    text = passage.text[offsets[start][0]:offsets[end - 1][1]]
                result.append(Passage(text, passage.page))
                if end == len(offsets):
                    break
                start = max(start + 1, end - 40)
        return result

    def encode(self, texts):
        self.load()
        return self._model.encode(texts)


class _MiniLM:
    """The model's documented Transformer + masked mean pooling inference path."""

    def __init__(self, location):
        from transformers import BertModel, BertTokenizerFast
        self.tokenizer = BertTokenizerFast.from_pretrained(str(location), local_files_only=True)
        self.max_seq_length = json.loads((location / "sentence_bert_config.json").read_text())["max_seq_length"]
        self.model = BertModel.from_pretrained(str(location), local_files_only=True).eval()

    def encode(self, texts):
        import torch
        result = []
        # Keep memory bounded when indexing large documents.
        with torch.inference_mode():
            for start in range(0, len(texts), 32):
                inputs = self.tokenizer(texts[start:start + 32], padding=True, truncation=True,
                                        max_length=self.max_seq_length, return_tensors="pt")
                tokens = self.model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1).expand(tokens.size()).float()
                pooled = (tokens * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                result.extend(torch.nn.functional.normalize(pooled, p=2, dim=1).tolist())
        return result
