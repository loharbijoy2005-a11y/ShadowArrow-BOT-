import { NextResponse } from 'next/server';

const API_URL = process.env.WIKIDATA_API_URL || 'https://www.wikidata.org/w/api.php';
const BOT_USER = process.env.WIKIDATA_BOT_USER || 'SHADOWARROW 2026@ShadowBot';
const BOT_PASSWORD = process.env.WIKIDATA_BOT_PASSWORD || '';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { qid, editId, fieldType, lang, previousValue } = body;

    if (!qid || !lang) {
      return NextResponse.json(
        { success: false, error: 'Missing required parameters: qid and lang' },
        { status: 400 }
      );
    }

    // Step 1: Perform login to Wikidata MediaWiki API
    const session = new Map<string, string>();
    const headers = {
      'User-Agent': 'ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) NextJS-Dashboard'
    };

    const loginTokenRes = await fetch(`${API_URL}?action=query&meta=tokens&type=login&format=json`, { headers });
    const loginTokenJson = await loginTokenRes.json();
    const loginToken = loginTokenJson?.query?.tokens?.logintoken;

    if (loginToken) {
      const loginParams = new URLSearchParams({
        action: 'login',
        lgname: BOT_USER,
        lgpassword: BOT_PASSWORD,
        lgtoken: loginToken,
        format: 'json'
      });

      const cookies = loginTokenRes.headers.get('set-cookie');
      
      const loginRes = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': headers['User-Agent'],
          ...(cookies ? { 'Cookie': cookies } : {})
        },
        body: loginParams.toString()
      });
      const loginJson = await loginRes.json();
      
      if (loginJson?.login?.result === 'Success') {
        const csrfRes = await fetch(`${API_URL}?action=query&meta=tokens&type=csrf&format=json`, {
          headers: {
            ...headers,
            ...(cookies ? { 'Cookie': cookies } : {})
          }
        });
        const csrfJson = await csrfRes.json();
        const csrfToken = csrfJson?.query?.tokens?.csrftoken;

        if (csrfToken) {
          // Revert label or description via wbeditentity
          const payload: any = {};
          if (fieldType.includes('label')) {
            payload.labels = {
              [lang]: previousValue ? { language: lang, value: previousValue } : { language: lang, remove: "" }
            };
          } else {
            payload.descriptions = {
              [lang]: previousValue ? { language: lang, value: previousValue } : { language: lang, remove: "" }
            };
          }

          const revertParams = new URLSearchParams({
            action: 'wbeditentity',
            id: qid,
            data: JSON.stringify(payload),
            summary: `Reverted bot edit on ${qid} via Next.js Admin Dashboard`,
            token: csrfToken,
            bot: '1',
            format: 'json'
          });

          await fetch(API_URL, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
              'User-Agent': headers['User-Agent'],
              ...(cookies ? { 'Cookie': cookies } : {})
            },
            body: revertParams.toString()
          });
        }
      }
    }

    return NextResponse.json({
      success: true,
      qid,
      editId,
      message: `Successfully dispatched rollback for ${qid} (${fieldType}). Field reverted.`
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message || 'Rollback execution failed' },
      { status: 500 }
    );
  }
}
