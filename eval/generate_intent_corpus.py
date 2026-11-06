import json
import os
from typing import List, Dict

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "vocative_corpus.jsonl")

SYNTHETIC_CORPUS: List[Dict] = [
    # =========================================================================
    # 1. English - Direct Address (Must Alert)
    # =========================================================================
    {"id": "en_dir_01", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Hey Alex, can you take over screen sharing for a moment?"},
    {"id": "en_dir_02", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex, please unmute and share your updates on the database migration."},
    {"id": "en_dir_03", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex, could you walk us through the deployment checklist?"},
    {"id": "en_dir_04", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Can you hear us clearly, Alex?"},
    {"id": "en_dir_05", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex, what do you think about splitting the service into two workers?"},
    {"id": "en_dir_06", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex?"},
    {"id": "en_dir_07", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Hi Alex, are you able to join the breakout room?"},
    {"id": "en_dir_08", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex, check the error logs on production when you get a chance."},
    {"id": "en_dir_09", "lang": "en", "target": "Alex", "label": "direct_address", "text": "So Alex, will you be leading the architecture review today?"},
    {"id": "en_dir_10", "lang": "en", "target": "Alex", "label": "direct_address", "text": "Alex, confirm if the security patch has been rolled out."},

    # =========================================================================
    # 2. English - Casual Mentions & Passive/Reporting (Must Suppress)
    # =========================================================================
    {"id": "en_cas_01", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "I was discussing this earlier in a meeting with Alex."},
    {"id": "en_cas_02", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "Alex merged the pull request an hour ago before leaving."},
    {"id": "en_cas_03", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "We reviewed Alex's presentation slides and sent our feedback."},
    {"id": "en_cas_04", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "I got this design document directly from Alex this morning."},
    {"id": "en_cas_05", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "According to Alex, the client requested a postponement."},
    {"id": "en_cas_06", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "This nasty database locking issue was fixed by Alex last week."},
    {"id": "en_cas_07", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "Please ask Alex if the staging server credentials were updated."},
    {"id": "en_cas_08", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "Alex wrote a very comprehensive design doc for this feature."},
    {"id": "en_cas_09", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "Someone tell Alex to push the release tag when ready."},
    {"id": "en_cas_10", "lang": "en", "target": "Alex", "label": "casual_mention", "text": "We compared our benchmark results against Alex's numbers."},

    # =========================================================================
    # 3. Banglish - Direct Address (Must Alert)
    # =========================================================================
    {"id": "bn_dir_01", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Alex ekkhuni meeting ta join koro."},
    {"id": "bn_dir_02", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Ei Alex, amader kotha sunte paccho?"},
    {"id": "bn_dir_03", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Alex-da, eita ki bhabe configure korbo bolo to?"},
    {"id": "bn_dir_04", "lang": "bn", "target": "Mayukh", "label": "direct_address", "text": "Mayukh, tumi eita ekbar check koro please."},
    {"id": "bn_dir_05", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Alex, shuno ekbar, screen ta share koro."},
    {"id": "bn_dir_06", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Arre Alex, bolte parbe kobe release hobe?"},
    {"id": "bn_dir_07", "lang": "bn", "target": "Mayukh", "label": "direct_address", "text": "Mayukh-da, apnar updates gulo ektu bolun."},
    {"id": "bn_dir_08", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Alex bhai, tumi ki call-e achho?"},
    {"id": "bn_dir_09", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Ei Alex, eitar response ta dekho ekbar."},
    {"id": "bn_dir_10", "lang": "bn", "target": "Alex", "label": "direct_address", "text": "Alex, tumi eita confirm koro."},

    # =========================================================================
    # 4. Banglish - Casual Mentions & Clitics (Must Suppress)
    # =========================================================================
    {"id": "bn_cas_01", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex-er shathe amar kotha hoyeche ajke sokale."},
    {"id": "bn_cas_02", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex boleche project ta submit kora hoye geche."},
    {"id": "bn_cas_03", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Eita Alex korechilo shokal bela."},
    {"id": "bn_cas_04", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex-ke jigyasha kore janabo ami pore."},
    {"id": "bn_cas_05", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex-er laptop ta suddenly freeze hoye gelo."},
    {"id": "bn_cas_06", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Ami Alex theke eita niyechilam kal."},
    {"id": "bn_cas_07", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex-er code review ta complete hoyeche."},
    {"id": "bn_cas_08", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Ei whole pipeline ta Alex baniyeche."},
    {"id": "bn_cas_09", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex ke bolo slack-e ping korte."},
    {"id": "bn_cas_10", "lang": "bn", "target": "Alex", "label": "casual_mention", "text": "Alex er kache file ta ache mone hoy."},

    # =========================================================================
    # 5. Hinglish - Direct Address (Must Alert)
    # =========================================================================
    {"id": "hi_dir_01", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Suno Alex, kya bol rahe ho tum?"},
    {"id": "hi_dir_02", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex bhai, zara screen share karna ek minute."},
    {"id": "hi_dir_03", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex, aap bataiye kya progress hai backend pe."},
    {"id": "hi_dir_04", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Arre Alex, sun rahe ho kya?"},
    {"id": "hi_dir_05", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex ji, please unmute karke batayein."},
    {"id": "hi_dir_06", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex, ye test cases run karoge abhi?"},
    {"id": "hi_dir_07", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Hey Alex, tumhara mic shyd muted hai."},
    {"id": "hi_dir_08", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex, can you take this forward please?"},
    {"id": "hi_dir_09", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Bhai Alex, eak bar look out karna issue pe."},
    {"id": "hi_dir_10", "lang": "hi", "target": "Alex", "label": "direct_address", "text": "Alex, suno to sahi ek minute."},

    # =========================================================================
    # 6. Hinglish - Casual Mentions & Ergative/Dative (Must Suppress)
    # =========================================================================
    {"id": "hi_cas_01", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ne bola tha ye bug fix ho gaya hai."},
    {"id": "hi_cas_02", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Maine Alex se kal baat ki thi is bare me."},
    {"id": "hi_cas_03", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ko bolo ki repo access de de."},
    {"id": "hi_cas_04", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ka code merge ho chuka hai main branch me."},
    {"id": "hi_cas_05", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Ye feature Alex dwara banaya gaya tha."},
    {"id": "hi_cas_06", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ne PR raise kar di thi dopahar me."},
    {"id": "hi_cas_07", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Hum Alex ke presentation ka wait kar rahe the."},
    {"id": "hi_cas_08", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Ye document Alex ke taraf se aya hai."},
    {"id": "hi_cas_09", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ne bataya tha client happy hai."},
    {"id": "hi_cas_10", "lang": "hi", "target": "Alex", "label": "casual_mention", "text": "Alex ke sath review schedule kar do."},

    # =========================================================================
    # 7. Modal Homophones & Ambiguous Names (Stress Test)
    # =========================================================================
    {"id": "homo_01", "lang": "en", "target": "Will", "label": "casual_mention", "text": "Will this work for our next deployment cycle?"},
    {"id": "homo_02", "lang": "en", "target": "Will", "label": "casual_mention", "text": "Will anyone be able to cover the support shift?"},
    {"id": "homo_03", "lang": "en", "target": "Will", "label": "direct_address", "text": "Hey Will, can you check the server metrics?"},
    {"id": "homo_04", "lang": "en", "target": "Will", "label": "direct_address", "text": "Will, please unmute and confirm the release tag."},
    {"id": "homo_05", "lang": "en", "target": "May", "label": "casual_mention", "text": "May I ask what the deadline is for this ticket?"},
    {"id": "homo_06", "lang": "en", "target": "May", "label": "casual_mention", "text": "May we proceed with the cloud rollout now?"},
    {"id": "homo_07", "lang": "en", "target": "May", "label": "direct_address", "text": "Hey May, what are your thoughts on this API design?"},
    {"id": "homo_08", "lang": "en", "target": "Mark", "label": "casual_mention", "text": "Please mark this ticket as resolved in Jira."},
    {"id": "homo_09", "lang": "en", "target": "Mark", "label": "direct_address", "text": "Mark, can you take notes for this meeting?"},
    {"id": "homo_10", "lang": "en", "target": "Rob", "label": "direct_address", "text": "Hey Rob, are you on the call?"},

    # =========================================================================
    # 8. Native Bengali & Devanagari Hindi Script
    # =========================================================================
    {"id": "script_bn_dir_01", "lang": "bn", "target": "এলেক্স", "label": "direct_address", "text": "এলেক্স, তুমি কি শুনতে পাচ্ছ?"},
    {"id": "script_bn_dir_02", "lang": "bn", "target": "ময়ূখ", "label": "direct_address", "text": "ময়ূখদা, এই স্ক্রিনটা একবার দেখুন।"},
    {"id": "script_bn_cas_01", "lang": "bn", "target": "এলেক্স", "label": "casual_mention", "text": "এলেক্সের সাথে কথা হয়েছে কাল।"},
    {"id": "script_bn_cas_02", "lang": "bn", "target": "এলেক্স", "label": "casual_mention", "text": "এলেক্স বলেছে কাজটা শেষ হয়েছে।"},
    {"id": "script_hi_dir_01", "lang": "hi", "target": "एलेक्स", "label": "direct_address", "text": "सुनो एलेक्स, क्या तुम स्क्रीन शेयर कर सकते हो?"},
    {"id": "script_hi_dir_02", "lang": "hi", "target": "एलेक्स", "label": "direct_address", "text": "एलेक्स जी, कृपया बताइए।"},
    {"id": "script_hi_cas_01", "lang": "hi", "target": "एलेक्स", "label": "casual_mention", "text": "एलेक्स ने बोला था सब ठीक है।"},
    {"id": "script_hi_cas_02", "lang": "hi", "target": "एलेक्स", "label": "casual_mention", "text": "यह काम एलेक्स द्वारा किया गया था।"}
]

def generate_corpus():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for item in SYNTHETIC_CORPUS:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated {len(SYNTHETIC_CORPUS)} annotated multilingual vocative samples in: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_corpus()
