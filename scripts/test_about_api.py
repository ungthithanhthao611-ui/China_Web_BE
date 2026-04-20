"""Test script for /public/pages/about API endpoint."""
import json
import requests

URL = "http://localhost:8001/api/v1/public/pages/about"

r = requests.get(URL)
print(f"STATUS: {r.status_code}")

if r.status_code != 200:
    print("ERROR:", r.text)
    exit(1)

data = r.json()

print(f"SLUG: {data.get('slug')}")
print(f"TITLE: {data.get('title')}")
print(f"PAGE_TYPE: {data.get('page_type')}")
print(f"META_TITLE: {data.get('meta_title')}")

sections = data.get("sections", [])
print(f"\n=== SECTIONS ({len(sections)}) ===")
for s in sections:
    print(f"  [{s['id']}] anchor={s['anchor']} | title={s['title']} | type={s.get('section_type')}")

blocks = data.get("blocks", [])
total_items = sum(len(b.get("items", [])) for b in blocks)
print(f"\n=== BLOCKS ({len(blocks)}) | TOTAL ITEMS: {total_items} ===")
for b in blocks:
    items = b.get("items", [])
    print(f"  [{b['id']}] key={b['block_key']} | type={b['block_type']} | items={len(items)}")
    for it in items[:3]:
        meta_str = json.dumps(it.get("metadata_json") or {}, ensure_ascii=False)[:80]
        print(f"      item_key={it['item_key']} | title={str(it.get('title',''))[:60]} | meta={meta_str}")
    if len(items) > 3:
        print(f"      ... +{len(items) - 3} more items")

gallery = data.get("gallery", [])
print(f"\n=== GALLERY ({len(gallery)}) ===")

# Checklist
print("\n=== CHECKLIST ===")
block_keys = {b["block_key"] for b in blocks}
required_keys = [
    "hero_summary", "hero_nav",
    "intro_media", "intro_video", "intro_paragraphs",
    "speech_profile", "speech_body", "speech_signature",
    "org_chart_image",
    "culture_purpose", "culture_mission", "culture_spirit", "culture_values",
    "timeline",
    "leadership_care_gallery",
    "partner_categories", "partner_logos",
]
all_ok = True
for key in required_keys:
    found = key in block_keys
    items_count = 0
    for b in blocks:
        if b["block_key"] == key:
            items_count = len(b.get("items", []))
    status = "OK" if found and items_count > 0 else "MISSING"
    if status == "MISSING":
        all_ok = False
    print(f"  {status}: {key} ({items_count} items)")

section_anchors = {s["anchor"] for s in sections}
required_sections = [
    "hero", "company_introduction", "chairman_speech", "organization_chart",
    "corporate_culture", "development_course", "leadership_care", "cooperative_partner",
]
for anchor in required_sections:
    found = anchor in section_anchors
    status = "OK" if found else "MISSING"
    if not found:
        all_ok = False
    print(f"  {status}: section/{anchor}")

print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
