import { NextResponse } from 'next/server';

export interface EditRecord {
  id: string;
  qid: string;
  fieldType: 'hi_label' | 'bn_label' | 'hi_desc' | 'bn_desc';
  fieldLabel: string;
  lang: 'hi' | 'bn';
  oldValue: string | null;
  newValue: string;
  status: 'VERIFIED_SAFE' | 'FLAGGED_ANOMALY';
  sitelinkSource: 'bnwiki' | 'hiwiki' | 'state_nlp' | 'transliteration';
  timestamp: string;
  latencyMs: number;
  reverted: boolean;
}

// Sample recent edits feed (simulating live Wikidata feed)
let recentEditsStore: EditRecord[] = [
  {
    id: 'edit-101',
    qid: 'Q138024003',
    fieldType: 'bn_label',
    fieldLabel: 'Label (Bengali)',
    lang: 'bn',
    oldValue: null,
    newValue: 'মাদকের জেলা',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'bnwiki',
    timestamp: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
    latencyMs: 1420,
    reverted: false
  },
  {
    id: 'edit-102',
    qid: 'Q138024003',
    fieldType: 'hi_label',
    fieldLabel: 'Label (Hindi)',
    lang: 'hi',
    oldValue: null,
    newValue: 'मादक का ज़िला',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'hiwiki',
    timestamp: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
    latencyMs: 1380,
    reverted: false
  },
  {
    id: 'edit-103',
    qid: 'Q130977614',
    fieldType: 'bn_desc',
    fieldLabel: 'Description (Bengali)',
    lang: 'bn',
    oldValue: null,
    newValue: 'ভারতের পশ্চিমবঙ্গ রাজ্যের একটি শহর',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'state_nlp',
    timestamp: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    latencyMs: 1840,
    reverted: false
  },
  {
    id: 'edit-104',
    qid: 'Q130977614',
    fieldType: 'hi_desc',
    fieldLabel: 'Description (Hindi)',
    lang: 'hi',
    oldValue: null,
    newValue: 'भारत के पश्चिम बंगाल राज्य का एक शहर',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'state_nlp',
    timestamp: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    latencyMs: 1720,
    reverted: false
  },
  {
    id: 'edit-105',
    qid: 'Q12498001',
    fieldType: 'bn_label',
    fieldLabel: 'Label (Bengali)',
    lang: 'bn',
    oldValue: null,
    newValue: 'আহমেদাবাদ',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'bnwiki',
    timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    latencyMs: 1910,
    reverted: false
  },
  {
    id: 'edit-106',
    qid: 'Q22608963',
    fieldType: 'hi_label',
    fieldLabel: 'Label (Hindi)',
    lang: 'hi',
    oldValue: null,
    newValue: 'गांधीनगर',
    status: 'VERIFIED_SAFE',
    sitelinkSource: 'hiwiki',
    timestamp: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
    latencyMs: 1650,
    reverted: false
  }
];

export async function GET(request: Request) {
  return NextResponse.json({
    success: true,
    edits: recentEditsStore,
    total: recentEditsStore.length
  });
}
