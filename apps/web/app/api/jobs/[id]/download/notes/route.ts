import { NextRequest } from 'next/server';

const API_URL = process.env.API_URL || 'http://api:8000';

export async function GET(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const jobId = params.id;
        const response = await fetch(`${API_URL}/jobs/${jobId}/download/notes`, {
            method: 'GET',
        });

        if (!response.ok) {
            return new Response('Notes file not found', { status: response.status });
        }

        return new Response(response.body, {
            headers: {
                'Content-Type': 'text/markdown',
                'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment; filename="notes.md"',
            },
        });
    } catch (error: any) {
        console.error('Download proxy error:', error);
        return new Response('Failed to download notes', { status: 500 });
    }
}
