import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'http://api:8000';

export async function GET(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const jobId = params.id;
        const response = await fetch(`${API_URL}/jobs/${jobId}`, {
            method: 'GET',
        });

        const data = await response.json();

        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        console.error('API proxy error:', error);
        return NextResponse.json(
            { detail: error.message || 'Failed to get job' },
            { status: 500 }
        );
    }
}

export async function DELETE(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const jobId = params.id;
        const response = await fetch(`${API_URL}/jobs/${jobId}`, {
            method: 'DELETE',
        });

        const data = await response.json();

        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        console.error('API proxy error:', error);
        return NextResponse.json(
            { detail: error.message || 'Failed to delete job' },
            { status: 500 }
        );
    }
}
