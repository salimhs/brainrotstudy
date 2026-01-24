import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'http://api:8000';

export async function POST(request: NextRequest) {
    try {
        const contentType = request.headers.get('content-type') || '';

        let body: any;
        let headers: HeadersInit = {};

        if (contentType.includes('multipart/form-data')) {
            // For file uploads, forward the FormData as-is
            body = await request.formData();
        } else {
            // For JSON requests
            body = await request.text();
            headers['Content-Type'] = 'application/json';
        }

        const response = await fetch(`${API_URL}/jobs`, {
            method: 'POST',
            headers,
            body,
        });

        const data = await response.json();

        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        console.error('API proxy error:', error);
        return NextResponse.json(
            { detail: error.message || 'Failed to create job' },
            { status: 500 }
        );
    }
}
