export const dynamic = "force-dynamic";

import { NextResponse } from 'next/server';

async function* streamToIterator(stream: ReadableStream<Uint8Array>): AsyncIterable<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }
      yield decoder.decode(value);
    }
  } finally {
    reader.releaseLock();
  }
}

export async function POST(req: Request) {
  try {
    console.log('开始发送请求进行搜索');
    const body = await req.json();
    const { message, history = [], search_result = [] } = body;

    const backendUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!backendUrl) {
      return NextResponse.json({ error: 'Backend URL is not configured' }, { status: 500 });
    }

    const response = await fetch(`${backendUrl}/search/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, history, search_result }),
    });

    if (!response.body) {
      return NextResponse.json({ error: 'Backend response has no body' }, { status: 500 });
    }

    const readableStream = new ReadableStream({
      async start(controller) {
        for await (const chunk of streamToIterator(response.body!)) {
          controller.enqueue(new TextEncoder().encode(chunk));
        }
        controller.close();
      },
    });

    return new Response(readableStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('Error in search stream:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}