import { NextResponse } from 'next/server';

const API_URL = 'https://www.wikidata.org/w/api.php';
const USER_AGENT = 'ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) NextJS-Dashboard';

const BENGALI_SCRIPT_REGEX = /[\u0980-\u09FF]/;
const DEVANAGARI_SCRIPT_REGEX = /[\u0900-\u097F]/;
const LATIN_ALPHABET_REGEX = /[a-zA-Z]/;

const INDIAN_STATES: Record<string, { hi: string; bn: string }> = {
  "Andhra Pradesh": { hi: "आंध्र प्रदेश", bn: "অন্ধ্রপ্রদেশ" },
  "Arunachal Pradesh": { hi: "अरुणाचल प्रदेश", bn: "অরুণাচল প্রদেশ" },
  "Assam": { hi: "असम", bn: "অসম" },
  "Bihar": { hi: "बिहार", bn: "বিহার" },
  "Chhattisgarh": { hi: "छत्तीसगढ़", bn: "ছত্তিশগড়" },
  "Goa": { hi: "गोवा", bn: "গোয়া" },
  "Gujarat": { hi: "गुजरात", bn: "গুজরাত" },
  "Haryana": { hi: "हरियाणा", bn: "হরিয়ানা" },
  "Himachal Pradesh": { hi: "हिमाचल प्रदेश", bn: "হিমাচল প্রদেশ" },
  "Jharkhand": { hi: "झारखंड", bn: "ঝাড়খণ্ড" },
  "Karnataka": { hi: "कर्नाटक", bn: "কর্ণাটক" },
  "Kerala": { hi: "केरल", bn: "কেরালা" },
  "Madhya Pradesh": { hi: "मध्य प्रदेश", bn: "मध्यप्रदेश" },
  "Maharashtra": { hi: "महाराष्ट्र", bn: "মহারাষ্ট্র" },
  "Manipur": { hi: "मणिपुर", bn: "মণিপুর" },
  "Meghalaya": { hi: "मेघालय", bn: "মেঘালয়" },
  "Mizoram": { hi: "मिजोरम", bn: "মিজোরাম" },
  "Nagaland": { hi: "नागालैंड", bn: "নাগাল্যান্ড" },
  "Odisha": { hi: "ओडिशा", bn: "ওড়িশা" },
  "Punjab": { hi: "पंजाब", bn: "পাঞ্জাব" },
  "Rajasthan": { hi: "राजस्थान", bn: "রাজস্থান" },
  "Sikkim": { hi: "सिक्किम", bn: "সিকিম" },
  "Tamil Nadu": { hi: "तमिलनाडु", bn: "তামিলনাড়ু" },
  "Telangana": { hi: "तेलंगाना", bn: "तेलेंगाना" },
  "Tripura": { hi: "त्रिपुरा", bn: "ত্রিপুরা" },
  "Uttar Pradesh": { hi: "उत्तर प्रदेश", bn: "उत्तरप्रदेश" },
  "Uttarakhand": { hi: "उत्तराखंड", bn: "উত্তরাখণ্ড" },
  "West Bengal": { hi: "पश्चिम बंगाल", bn: "পশ্চিমবঙ্গ" },
  "Delhi": { hi: "दिल्ली", bn: "দিল্লি" },
  "Jammu and Kashmir": { hi: "जम्मू और कश्मीर", bn: "জম্মু ও কাশ্মীর" },
  "Ladakh": { hi: "लद्दाख", bn: "লাদাখ" },
  "Puducherry": { hi: "पुदुचेरी", bn: "পুদুচেরি" },
  "Chandigarh": { hi: "चंडीगढ़", bn: "चंडीगढ़" }
};

function validateScript(text: string, lang: 'hi' | 'bn'): boolean {
  if (!text || LATIN_ALPHABET_REGEX.test(text)) return false;
  return lang === 'bn' ? BENGALI_SCRIPT_REGEX.test(text) : DEVANAGARI_SCRIPT_REGEX.test(text);
}

function cleanSitelinkTitle(title: string): string {
  if (!title) return '';
  return title.replace(/\s*\([^)]*\)$/, '').trim();
}

function parseEnglishDescription(enDesc: string): { entityType: string; stateName: string } | null {
  if (!enDesc) return null;
  const descClean = enDesc.trim();

  const patterns = [
    { regex: /\b(?:city|town|human settlement|municipality)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$/i, type: 'city' },
    { regex: /\b(?:village|gram panchayat)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$/i, type: 'village' },
    { regex: /\b(?:district|administrative district)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$/i, type: 'district' },
    { regex: /\b(?:river|watercourse|tributary)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$/i, type: 'river' }
  ];

  for (const { regex, type } of patterns) {
    const match = descClean.match(regex);
    if (match) {
      const extractedState = match[1].replace(/\s+state$/i, '').trim();
      for (const stateKey of Object.keys(INDIAN_STATES)) {
        if (stateKey.toLowerCase() === extractedState.toLowerCase()) {
          return { entityType: type, stateName: stateKey };
        }
      }
    }
  }

  return null;
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    let qid = (body.qid || '').trim().toUpperCase();

    if (!qid.startsWith('Q') || !/^\d+$/.test(qid.slice(1))) {
      return NextResponse.json(
        { success: false, error: 'Invalid QID format. Example: Q1156' },
        { status: 400 }
      );
    }

    const params = new URLSearchParams({
      action: 'wbgetentities',
      ids: qid,
      props: 'labels|descriptions|sitelinks',
      sitefilter: 'bnwiki|hiwiki',
      languages: 'en|bn|hi',
      format: 'json'
    });

    const res = await fetch(`${API_URL}?${params.toString()}`, {
      headers: { 'User-Agent': USER_AGENT }
    });
    const data = await res.json();
    const entity = data?.entities?.[qid];

    if (!entity || entity.missing !== undefined) {
      return NextResponse.json(
        { success: false, error: `Entity ${qid} does not exist on Wikidata.` },
        { status: 404 }
      );
    }

    const labels = entity.labels || {};
    const descriptions = entity.descriptions || {};
    const sitelinks = entity.sitelinks || {};

    const enLabel = labels.en?.value || '';
    const enDesc = descriptions.en?.value || '';

    const bnwikiTitle = sitelinks.bnwiki?.title || null;
    const hiwikiTitle = sitelinks.hiwiki?.title || null;

    const payloadLabels: Record<string, { language: string; value: string }> = {};
    const payloadDescriptions: Record<string, { language: string; value: string }> = {};

    // 1. Label Dry-Run Simulation (Sitelink-Only Mode)
    if (!labels.hi && hiwikiTitle) {
      const cleanHi = cleanSitelinkTitle(hiwikiTitle);
      if (validateScript(cleanHi, 'hi')) {
        payloadLabels.hi = { language: 'hi', value: cleanHi };
      }
    }

    if (!labels.bn && bnwikiTitle) {
      const cleanBn = cleanSitelinkTitle(bnwikiTitle);
      if (validateScript(cleanBn, 'bn')) {
        payloadLabels.bn = { language: 'bn', value: cleanBn };
      }
    }

    // 2. Description Dry-Run Simulation
    const parsedState = parseEnglishDescription(enDesc);
    let stateMapping = null;

    if (parsedState) {
      const { entityType, stateName } = parsedState;
      const stateMap = INDIAN_STATES[stateName];
      if (stateMap) {
        stateMapping = {
          entityType,
          stateName,
          hi: stateMap.hi,
          bn: stateMap.bn
        };

        if (entityType === 'city' || entityType === 'town') {
          if (!descriptions.hi) payloadDescriptions.hi = { language: 'hi', value: `भारत के ${stateMap.hi} राज्य का एक शहर` };
          if (!descriptions.bn) payloadDescriptions.bn = { language: 'bn', value: `ভারতের ${stateMap.bn} রাজ্যের একটি শহর` };
        } else if (entityType === 'village') {
          if (!descriptions.hi) payloadDescriptions.hi = { language: 'hi', value: `भारत के ${stateMap.hi} राज्य का एक गाँव` };
          if (!descriptions.bn) payloadDescriptions.bn = { language: 'bn', value: `ভারতের ${stateMap.bn} রাজ্যের একটি গ্রাম` };
        } else if (entityType === 'district') {
          if (!descriptions.hi) payloadDescriptions.hi = { language: 'hi', value: `भारत के ${stateMap.hi} राज्य का एक ज़िला` };
          if (!descriptions.bn) payloadDescriptions.bn = { language: 'bn', value: `ভারতের ${stateMap.bn} রাজ্যের একটি জেলা` };
        } else if (entityType === 'river') {
          if (!descriptions.hi) payloadDescriptions.hi = { language: 'hi', value: `भारत के ${stateMap.hi} राज्य की एक नदी` };
          if (!descriptions.bn) payloadDescriptions.bn = { language: 'bn', value: `ভারতের ${stateMap.bn} রাজ্যের একটি নদী` };
        }
      }
    }

    const intendedPayload: any = {};
    if (Object.keys(payloadLabels).length > 0) intendedPayload.labels = payloadLabels;
    if (Object.keys(payloadDescriptions).length > 0) intendedPayload.descriptions = payloadDescriptions;

    const isTargetable = Object.keys(intendedPayload).length > 0;

    return NextResponse.json({
      success: true,
      inspection: {
        qid,
        enLabel,
        enDesc,
        existingLabels: {
          hi: labels.hi?.value || null,
          bn: labels.bn?.value || null
        },
        existingDescriptions: {
          hi: descriptions.hi?.value || null,
          bn: descriptions.bn?.value || null
        },
        sitelinks: {
          bnwiki: bnwikiTitle,
          hiwiki: hiwikiTitle
        },
        stateMapping,
        intendedPayload,
        isTargetable,
        validationPassed: true
      }
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message || 'Inspection failed' },
      { status: 500 }
    );
  }
}
