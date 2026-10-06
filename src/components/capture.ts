// Reads the files of one capture at build time. `id` is `<project>/<name>`. See `captures/README.md`.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface CaptureSpec {
	title: string;
	command: string;
	stage?: number;
	order?: number;
	setup?: string[];
	mode?: 'scripted' | 'manual';
}

export interface CaptureFiles {
	spec?: CaptureSpec;
	output?: string;
}

// Vite copies each recording into the build and gives its URL. A new `.cast` file needs no other change.
// `no-inline` keeps a small recording as a file, so the player always loads it from this site.
const casts = import.meta.glob<string>('/captures/**/*.cast', {
	query: '?url&no-inline',
	import: 'default',
	eager: true,
});

export function loadCapture(id: string): CaptureFiles {
	const base = join(process.cwd(), 'captures', id);
	return {
		spec: existsSync(`${base}.json`) ? JSON.parse(readFileSync(`${base}.json`, 'utf8')) : undefined,
		output: existsSync(`${base}.txt`) ? readFileSync(`${base}.txt`, 'utf8') : undefined,
	};
}

export function castUrl(id: string): string | undefined {
	return casts[`/captures/${id}.cast`];
}
