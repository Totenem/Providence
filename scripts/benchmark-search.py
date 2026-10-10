"""Reproducible synthetic retrieval smoke benchmark, not an independent leaderboard."""

import argparse
import json
import math
from pathlib import Path
import sys
import time
import platform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from providence.embeddings import LocalEmbedder, QwenEmbedder
from providence.engine import Engine
from providence.store import Store

# Fictional personal files with paraphrases, mixed-language queries and exact IDs.
CASES = [
    (
        "A PostgreSQL proposal for a campus library tracks borrowed books, students and overdue loans.",
        [
            "campus library database design",
            "the proposal about borrowing books",
            "tables for overdue student loans",
            "panukala para sa database ng aklatan",
            "mga librong hiniram ng estudyante",
            "library proposal na ginawa ko",
        ],
    ),
    (
        "A Cebu beach holiday itinerary lists the ferry departure, ocean swimming and a seaside hotel reservation.",
        [
            "Cebu beach travel itinerary",
            "where we booked the seaside hotel",
            "the ferry for our swimming holiday",
            "plano ng bakasyon sa dagat sa Cebu",
            "reserbasyon ng hotel sa tabing dagat",
            "Cebu trip na may ferry",
        ],
    ),
    (
        "Meeting minutes cover the website redesign, navigation menu and the launch deadline assigned to the design team.",
        [
            "website redesign meeting minutes",
            "the discussion about the new navigation menu",
            "design team launch deadline",
            "tala ng pulong tungkol sa bagong website",
            "takdang petsa ng paglulunsad ng site",
            "meeting notes ng design team",
        ],
    ),
    (
        "A recipe for chocolate banana bread lists ripe bananas, cocoa powder, flour and a forty-minute baking time.",
        [
            "chocolate banana bread recipe",
            "the instructions for baking with ripe bananas",
            "cocoa loaf baking time",
            "resipe ng tinapay na may saging at tsokolate",
            "paraan ng pagluluto ng banana bread",
            "banana bread recipe na may cocoa",
        ],
    ),
    (
        "A monthly household budget allocates money for rent, groceries, electricity and emergency savings.",
        [
            "monthly household expense budget",
            "the allocation for rent and groceries",
            "our emergency savings plan",
            "buwanang badyet ng pamilya",
            "gastos sa upa pagkain at kuryente",
            "budget para sa household bills",
        ],
    ),
    (
        "A resume describes three years of Python development, SQL analysis and an internship building backend APIs.",
        [
            "Python developer resume",
            "my backend internship experience",
            "three years of programming work history",
            "resume para sa trabaho bilang programmer",
            "karanasan ko sa paggawa ng backend",
            "CV ko na may Python at SQL",
        ],
    ),
    (
        "Class notes explain photosynthesis, chlorophyll, sunlight and how plants convert carbon dioxide into sugars.",
        [
            "photosynthesis biology notes",
            "how sunlight helps plants make sugar",
            "the explanation of chlorophyll",
            "tala sa klase tungkol sa photosynthesis",
            "paano gumagawa ng pagkain ang halaman",
            "biology notes na may chlorophyll",
        ],
    ),
    (
        "A car maintenance receipt records replacement brake pads, an engine oil change and tire rotation.",
        [
            "car maintenance receipt",
            "the mechanic replaced our brake pads",
            "engine oil and tire service record",
            "resibo ng pagkukumpuni ng kotse",
            "pagpapalit ng langis at preno",
            "car service receipt na may tires",
        ],
    ),
    (
        "An apartment rental agreement specifies the monthly rent, security deposit and the landlord contact details.",
        [
            "apartment rental agreement",
            "the contract with our landlord",
            "security deposit for the apartment",
            "kasunduan sa pag-upa ng apartment",
            "kontrata at deposito sa inuupahang bahay",
            "rental contract na may landlord contact",
        ],
    ),
    (
        "A wedding invitation includes the ceremony venue, reception dinner and the RSVP deadline for guests.",
        [
            "wedding invitation",
            "the reception dinner location",
            "guest RSVP deadline",
            "imbitasyon sa kasal",
            "lugar ng seremonya at handaan",
            "wedding invite na may RSVP",
        ],
    ),
    (
        "A gym training schedule alternates strength exercises, running intervals and recovery rest days.",
        [
            "gym training schedule",
            "my strength and running workout plan",
            "which days are for recovery",
            "iskedyul ng ehersisyo sa gym",
            "plano ng pagtakbo at pagpapalakas",
            "workout plan na may rest days",
        ],
    ),
    (
        "A router setup guide explains the Wi-Fi network name, password configuration and resetting the wireless connection.",
        [
            "router Wi-Fi setup guide",
            "how we configured the wireless password",
            "resetting our network connection",
            "gabay sa pag-set up ng Wi-Fi",
            "pagpapalit ng password ng router",
            "router instructions para sa network",
        ],
    ),
    (
        "A pet vaccination record lists a cat rabies booster, the veterinary clinic and the next appointment date.",
        [
            "cat vaccination record",
            "our veterinary rabies booster appointment",
            "the next visit to the pet clinic",
            "tala ng bakuna ng pusa",
            "susunod na appointment sa beterinaryo",
            "cat vaccine record na may rabies",
        ],
    ),
    (
        "A gardening checklist covers planting tomatoes, watering seedlings and adding compost to the vegetable beds.",
        [
            "tomato gardening checklist",
            "watering the vegetable seedlings",
            "compost for our planting beds",
            "listahan ng gagawin sa pagtatanim",
            "pagdidilig ng mga punla ng kamatis",
            "garden notes na may compost",
        ],
    ),
    (
        "A scholarship application essay explains volunteer work, academic achievements and plans to study engineering.",
        [
            "scholarship application essay",
            "the essay about volunteering and academic awards",
            "my plans to study engineering",
            "sanaysay para sa scholarship",
            "aplikasyon para sa tulong sa pag-aaral",
            "scholarship essay na may volunteer work",
        ],
    ),
    (
        "A photography invoice itemizes the portrait session, edited digital photos and final payment balance.",
        [
            "portrait photography invoice",
            "the bill for edited digital photos",
            "remaining balance for the photo session",
            "singil para sa pagkuha ng litrato",
            "bayarin sa portrait session",
            "photography invoice na may edited photos",
        ],
    ),
    (
        "A laptop warranty document contains the serial number, repair coverage and the purchase expiration date.",
        [
            "laptop warranty document",
            "the repair coverage for my computer",
            "when our laptop warranty expires",
            "dokumento ng warranty ng laptop",
            "saklaw ng pagkukumpuni ng computer",
            "laptop warranty na may serial number",
        ],
    ),
    (
        "A concert ticket lists the orchestra performance, assigned seat and theater entry time.",
        [
            "orchestra concert ticket",
            "my assigned seat at the theater",
            "what time to enter the musical performance",
            "tiket para sa konsiyerto",
            "upuan ko sa pagtatanghal ng orkestra",
            "concert ticket na may theater seat",
        ],
    ),
    (
        "A project report analyzes solar panel output, daily sunlight exposure and electricity generation efficiency.",
        [
            "solar panel project report",
            "the analysis of sunlight and power output",
            "electricity generation efficiency study",
            "ulat tungkol sa solar panels",
            "pag-aaral ng kuryente mula sa araw",
            "solar report na may daily output",
        ],
    ),
    (
        "An equipment inventory lists office monitors, keyboards, desks and asset numbers for each workstation.",
        [
            "office equipment inventory",
            "the list of monitors and keyboards",
            "workstation asset numbers",
            "imbentaryo ng kagamitan sa opisina",
            "listahan ng mesa at monitor",
            "office inventory na may asset numbers",
        ],
    ),
    (
        "A customer support transcript describes a delayed parcel, delivery tracking and a requested shipping refund.",
        [
            "delayed parcel customer support transcript",
            "the conversation about our shipping refund",
            "tracking a late delivery",
            "usapan tungkol sa naantalang padala",
            "reklamo sa paghahatid ng pakete",
            "support chat na may shipping refund",
        ],
    ),
    (
        "A history essay describes the Spanish colonial period in the Philippines and the events leading to independence.",
        [
            "Philippine colonial history essay",
            "the events before independence from Spain",
            "my paper about the Spanish colonial period",
            "sanaysay sa kasaysayan ng Pilipinas",
            "mga pangyayari bago ang kalayaan",
            "history essay na may Spanish colonial period",
        ],
    ),
    (
        "A software test plan covers user login, password reset and validating access permissions for account roles.",
        [
            "software login test plan",
            "checks for resetting account passwords",
            "validating role access permissions",
            "plano ng pagsubok sa software",
            "pagsusuri ng login at password reset",
            "test plan para sa user accounts",
        ],
    ),
    (
        "A moving checklist organizes packing boxes, changing the postal address and booking a furniture delivery truck.",
        [
            "moving house checklist",
            "booking a truck to move the furniture",
            "changing our postal address",
            "listahan para sa paglipat ng bahay",
            "pag-iimpake ng gamit at mga kahon",
            "moving checklist na may delivery truck",
        ],
    ),
    (
        "A language lesson introduces Japanese greetings, basic vocabulary and practice conversations for beginners.",
        [
            "Japanese beginner language lesson",
            "practice conversations and greetings",
            "basic Japanese vocabulary notes",
            "aralin sa wikang Hapon",
            "mga pagbati at salita sa Japanese",
            "Japanese lesson na may conversations",
        ],
    ),
]


class CachedQueries:
    def __init__(self, model, queries, vectors):
        self.model = model
        self.identity = model.identity
        self.cache = dict(zip(queries, vectors))

    def encode(self, texts):
        return self.model.encode(texts)

    def passages(self, passages):
        return self.model.passages(passages)

    def encode_queries(self, texts):
        return [self.cache[text] for text in texts]


def percentile(values, q):
    return float(np.percentile(values, q))


def run(profile, output):
    work = Path(".artifacts/benchmark") / profile
    documents = work / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    queries = []
    expected = []
    categories = []
    for i, (text, paraphrases) in enumerate(CASES, 1):
        name = f"case-{i:02}.txt"
        (documents / name).write_text(
            text + f" Reference identifier: REF{i:04}.", encoding="utf-8"
        )
        for j, query in enumerate(paraphrases + [f"REF{i:04}", name]):
            queries.append(query)
            expected.append(name)
            categories.append(
                "English"
                if j < 3
                else "Filipino"
                if j < 5
                else "Mixed"
                if j == 5
                else "Identifier"
                if j == 6
                else "Filename"
            )
    model = QwenEmbedder() if profile == "qwen" else LocalEmbedder()
    start = time.monotonic()
    vectors = (
        model.encode_queries(queries)
        if hasattr(model, "encode_queries")
        else model.encode(queries)
    )
    encoded = time.monotonic() - start
    store = Store(work / "data" / "index.sqlite3", model.identity)
    engine = Engine(store, CachedQueries(model, queries, vectors))
    start = time.monotonic()
    report = engine.index(documents, force=True)
    indexing = time.monotonic() - start
    scores = []
    lookup = []
    by_category = {}
    for query, target, category in zip(queries, expected, categories):
        start = time.monotonic()
        results = engine.search(query, limit=10)
        lookup.append((time.monotonic() - start) * 1000)
        rank = next(
            (
                j + 1
                for j, result in enumerate(results)
                if Path(result.path).name == target
            ),
            None,
        )
        score = dict(
            hit1=int(rank == 1),
            hit5=int(rank is not None and rank <= 5),
            ndcg=1 / math.log2(rank + 1) if rank else 0,
        )
        scores.append(score)
        by_category.setdefault(category, []).append(score)
    warm = []
    for query in queries[:15]:
        start = time.monotonic()
        model.encode_queries([query]) if hasattr(
            model, "encode_queries"
        ) else model.encode([query])
        warm.append((time.monotonic() - start) * 1000)

    def aggregate(items):
        return {
            key: round(sum(item[key] for item in items) / len(items), 4)
            for key in ("hit1", "hit5", "ndcg")
        }

    result = dict(
        profile=profile,
        model=model.identity,
        platform=platform.platform(),
        python=platform.python_version(),
        documents=len(CASES),
        queries=len(queries),
        synthetic=True,
        quality=aggregate(scores),
        categories={key: aggregate(items) for key, items in by_category.items()},
        query_batch_seconds=round(encoded, 3),
        index_seconds=round(indexing, 3),
        warm_encoder_p95_ms=round(percentile(warm, 95), 3),
        cached_query_hybrid_lookup_p95_ms=round(percentile(lookup, 95), 3),
        indexing_issues=report.errors,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    engine.ocr_worker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["minilm", "qwen"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.profile, args.output)
