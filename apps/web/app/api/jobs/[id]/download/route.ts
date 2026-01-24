import { NextRequest } from 'next/server';

const API_URL = process.env.API_URL || 'http://api:8000';

export async function GET(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const jobId = params.id;
        const response = await fetch(`${API_URL}/jobs/${jobId}/download`, {
            method: 'GET',
        });

        if (!response.ok) {
            return new Response('Video not found', { status: response.status });
        }

        // Stream the video file
        return new Response(response.body, {
            headers: {
                'Content-Type': 'video/mp4',
                'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment; filename="video.mp4"',
            },
        });
    } catch (error: any) {
        console.error('Download proxy error:', error);
        return new Response('Failed to download video', { status: 500 });
    }
}
