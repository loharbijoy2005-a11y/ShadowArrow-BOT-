import { NextResponse } from 'next/server';

let currentBotStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED' = 'RUNNING';
let currentDelay = 1.8;

export async function GET() {
  return NextResponse.json({
    success: true,
    stats: {
      totalEditsToday: 142,
      totalEditsLifetime: 1284,
      anomalyRate: 0.0,
      botStatus: currentBotStatus,
      sitelinkHitRate: 96.4,
      requestDelay: currentDelay,
      verifiedCount: 1284,
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
