import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL;
  console.log('Backend URL:', backendUrl);
  const response = await fetch(`${backendUrl}/ping`);
  if (response.ok) {
    const text = await response.text();
    console.log('Backend response:', text);
    return NextResponse.json({ message: 'ok' });
  } else {
    return NextResponse.json({ error: 'Backend API request failed' }, { status: response.status });
  }
}
