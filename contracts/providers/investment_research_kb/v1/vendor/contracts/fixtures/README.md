# Release hash golden vectors

`release-hash-vectors.v1.json` is a language-neutral compatibility fixture for
`InvestmentResearchKB` and `invest_system`. Its expected values are literals,
not values that should be regenerated and committed automatically.

Consumer verification order:

1. Parse the fixture as UTF-8 JSON and require
   `canonicalization_profile == "irkb-jsonl-v1"`.
2. For each canonical JSON vector, apply the rules in the fixture and compare
   both the exact UTF-8 bytes and SHA-256 digest.
3. For each JSONL vector, sort records by the declared key tuple, serialize
   each record as canonical JSON, append one LF per record, and compare the
   byte length, exact bytes, and artifact digest.
4. For each Manifest vector, canonicalize `unsigned_manifest` without adding
   a newline and compare `expected_manifest_hash`. Then add that digest as
   `manifest_hash`, append one LF for the physical `manifest.json`, and compare
   the sealed file size and digest.

Do not substitute platform-native line endings, locale-aware sorting,
ASCII-escaped Unicode, insertion-order object serialization, a current
timestamp, or a newly generated release ID. Any mismatch is a contract failure.

`contract-locks.v1.json` pins both canonical JSON and exact physical-file
SHA-256 digests for every v1 contract. Do not update a v1 digest in place to
accommodate a schema change. Publish a new major contract file and a new lock
index instead. The repository forces LF endings for these files so the physical
digest is stable across platforms.

## Stage 6 reference consumer fixture

`stage6-reference-consumer.v1.json` is a small synthetic fixture for the
versioned `invest_system` integration boundary. It contains no production or
licensed source material. The fixture freezes:

- one published Evidence Bundle Release;
- one published Context Pack Release that points to the Evidence Release;
- a closed synthetic evidence-to-graph chain with a document, span, Fact,
  evidence link, two nodes, one edge, one evidence reference, and one source;
- one physical schema artifact beside each semantic artifact;
- canonical artifact byte lengths and SHA-256 values;
- two append-only `change-record.v1` publication records and opaque cursors;
- the exact five-field `strategy-input-ref.v1` expected from the Context Pack
  Release.

Consumers must reconstruct each inline semantic artifact as canonical UTF-8
JSON followed by one LF. An artifact value containing only
`fixture_contract_file` instead loads those exact physical bytes from the
parent `contracts/` directory; schema files deliberately retain their readable
non-canonical layout. Consumers then select by `artifact_id`, verify declared
size and SHA-256, validate schema identity and canonical schema hash, verify the
Manifest hash with `manifest_hash` omitted, and only then persist the input
reference. A schema artifact is never validated as an instance of itself.
Replaying the same release/change content is a no-op; reusing an ID with
different content is a contract failure. The fixture does not define a full
StrategyRunManifest and deliberately contains no gate, decision, position,
execution, or P&L fields.

`stage6-reference-consumer.v1.lock.json` pins the exact physical fixture
SHA-256. Changing the fixture therefore requires an explicit compatibility
review and lock update; consumers must not silently regenerate expected
values from an implementation under test.

`contract-locks.v1.json` remains the immutable Stage 5 lock index. Stage 6
contract additions are pinned separately in
`contract-locks.stage6.v1.json`; adding a Stage 6 contract must not rewrite the
historical index.
