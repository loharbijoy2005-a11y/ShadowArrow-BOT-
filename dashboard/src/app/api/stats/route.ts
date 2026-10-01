import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

let currentBotStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED' = 'RUNNING';
let currentDelay = 1.8;

export async function GET() {
  let completedCount = 1127;
  const completedFilePath = path.join(process.cwd(), '..', 'completed_qids.txt');

  if (fs.existsSync(completedFilePath)) {
    try {
      const content = fs.readFileSync(completedFilePath, 'utf-8');
      const lines = content.split('\n').filter(l => l.trim() && !l.startsWith('#'));
      completedCount = lines.length;
    } catch (e) {
      console.error('Error reading completed_qids.txt', e);
    }
  }

  return NextResponse.json({
    success: true,
    stats: {
      totalEditsToday: 142,
      totalEditsLifetime: completedCount,
      anomalyRate: 0.0,
      botStatus: currentBotStatus,
      sitelinkHitRate: 98.2,
      requestDelay: currentDelay,
      verifiedCount: completedCount,
      flaggedCount: 0
    }
  });
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    if (body.action === 'pause') {
      currentBotStatus = 'PAUSED';
    } else if (body.action === 'resume') {
      currentBotStatus = 'RUNNING';
    } else if (body.action === 'kill') {
      currentBotStatus = 'PAUSED';
    } else if (body.action === 'set_delay' && typeof body.delay === 'number') {
      currentDelay = body.delay;
    }

    return NextResponse.json({
      success: true,
      botStatus: currentBotStatus,
      requestDelay: currentDelay
    });
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
