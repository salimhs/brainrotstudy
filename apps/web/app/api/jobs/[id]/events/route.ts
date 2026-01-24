import { NextRequest } from 'next/server';

const API_URL = process.env.API_URL || 'http://api:8000';

export async function GET(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    const jobId = params.id;

    // Create a streaming response for SSE
    const stream = new ReadableStream({
        async start(controller) {
            try {
                const response = await fetch(`${API_URL}/jobs/${jobId}/events`, {
                    method: 'GET',
                    headers: {
                        'Accept': 'text/event-stream',
                    },
                });

                if (!response.ok || !response.body) {
                    controller.close();
                    return;
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();

                    if (done) {
                        controller.close();
                        break;
                    }

                    const chunk = decoder.decode(value, { stream: true });
                    controller.enqueue(new TextEncoder().encode(chunk));
                }
            } catch (error) {
                console.error('SSE proxy error:', error);
                controller.close();
            }
        },
    });

    return new Response(stream, {
        headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    });
}
