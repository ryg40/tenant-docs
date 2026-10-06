// Converts terminal output with ANSI codes to HTML at build time.
// A color becomes a class, and `src/styles/components.css` maps each class to the Soft Night palette.

interface Style {
	fg?: number;
	bg?: number;
	bold?: boolean;
	dim?: boolean;
	italic?: boolean;
	underline?: boolean;
	strike?: boolean;
	inverse?: boolean;
}

interface Segment {
	text: string;
	style: Style;
}

export interface AnsiResult {
	html: string;
	lines: number;
}

// One token: a CSI sequence, an OSC sequence, another escape sequence, or one control character.
const TOKEN =
	/\u001b\[([0-9;:?<=>!]*)[ -/]*([@-~])|\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)|\u001b[()#][0-9A-Za-z]|\u001b[@-Z\\^_`a-~=>]|[\u0000-\u001f\u007f]/g;

// The 16 colors of xterm. A 256-color or true-color value takes the nearest one, so the palette stays Soft Night.
const XTERM: [number, number, number][] = [
	[0, 0, 0],
	[205, 0, 0],
	[0, 205, 0],
	[205, 205, 0],
	[0, 0, 238],
	[205, 0, 205],
	[0, 205, 205],
	[229, 229, 229],
	[127, 127, 127],
	[255, 0, 0],
	[0, 255, 0],
	[255, 255, 0],
	[92, 92, 255],
	[255, 0, 255],
	[0, 255, 255],
	[255, 255, 255],
];

function nearest(r: number, g: number, b: number): number {
	let best = 0;
	let bestDistance = Infinity;
	XTERM.forEach(([xr, xg, xb], index) => {
		const distance = (r - xr) ** 2 + (g - xg) ** 2 + (b - xb) ** 2;
		if (distance < bestDistance) {
			best = index;
			bestDistance = distance;
		}
	});
	return best;
}

function from256(n: number): number {
	if (n < 16) return n;
	if (n >= 232) {
		const level = 8 + (n - 232) * 10;
		return nearest(level, level, level);
	}
	const cube = n - 16;
	const channel = (value: number) => (value === 0 ? 0 : 55 + value * 40);
	return nearest(channel(Math.floor(cube / 36)), channel(Math.floor(cube / 6) % 6), channel(cube % 6));
}

// Reads the color that follows the code 38 or 48. Returns the color and the count of parameters that it used.
function extended(params: number[], at: number): [number | undefined, number] {
	if (params[at] === 5 && params[at + 1] !== undefined) return [from256(params[at + 1]!), 2];
	if (params[at] === 2 && params[at + 3] !== undefined) {
		return [nearest(params[at + 1]!, params[at + 2]!, params[at + 3]!), 4];
	}
	return [undefined, params.length];
}

function applySgr(style: Style, raw: string): Style {
	const params = raw === '' ? [0] : raw.split(/[;:]/).map((part) => (part === '' ? 0 : Number(part)));
	let next = { ...style };
	for (let i = 0; i < params.length; i++) {
		const code = params[i]!;
		if (code === 0) next = {};
		else if (code === 1) next.bold = true;
		else if (code === 2) next.dim = true;
		else if (code === 3) next.italic = true;
		else if (code === 4) next.underline = true;
		else if (code === 7) next.inverse = true;
		else if (code === 9) next.strike = true;
		else if (code === 22) next.bold = next.dim = false;
		else if (code === 23) next.italic = false;
		else if (code === 24) next.underline = false;
		else if (code === 27) next.inverse = false;
		else if (code === 29) next.strike = false;
		else if (code >= 30 && code <= 37) next.fg = code - 30;
		else if (code === 39) next.fg = undefined;
		else if (code >= 40 && code <= 47) next.bg = code - 40;
		else if (code === 49) next.bg = undefined;
		else if (code >= 90 && code <= 97) next.fg = code - 90 + 8;
		else if (code >= 100 && code <= 107) next.bg = code - 100 + 8;
		else if (code === 38 || code === 48) {
			const [color, used] = extended(params, i + 1);
			if (code === 38) next.fg = color;
			else next.bg = color;
			i += used;
		}
	}
	return next;
}

function classes(style: Style): string {
	const list: string[] = [];
	if (style.inverse) {
		list.push(style.bg === undefined ? 'sn-fg-ground' : `sn-fg-${style.bg}`);
		list.push(style.fg === undefined ? 'sn-bg-ink' : `sn-bg-as-fg-${style.fg}`);
	} else {
		if (style.fg !== undefined) list.push(`sn-fg-${style.fg}`);
		if (style.bg !== undefined) list.push(`sn-bg-${style.bg}`);
	}
	if (style.bold) list.push('sn-bold');
	if (style.dim) list.push('sn-dim');
	if (style.italic) list.push('sn-italic');
	if (style.underline) list.push('sn-underline');
	if (style.strike) list.push('sn-strike');
	return list.join(' ');
}

function escapeHtml(text: string): string {
	return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderLine(segments: Segment[]): string {
	return segments
		.map(({ text, style }) => {
			const names = classes(style);
			return names ? `<span class="${names}">${escapeHtml(text)}</span>` : escapeHtml(text);
		})
		.join('');
}

export function ansiToHtml(input: string): AnsiResult {
	const lines: string[] = [];
	let line: Segment[] = [];
	let style: Style = {};

	const write = (text: string) => {
		if (text === '') return;
		const last = line[line.length - 1];
		if (last && last.style === style) last.text += text;
		else line.push({ text, style });
	};

	let position = 0;
	for (const match of input.matchAll(TOKEN)) {
		write(input.slice(position, match.index));
		position = match.index + match[0].length;
		const token = match[0];
		if (token === '\n') {
			lines.push(renderLine(line));
			line = [];
		} else if (token === '\r') {
			// A carriage return before a line feed ends the line. In other positions, the next text replaces the line.
			if (input[position] !== '\n') line = [];
		} else if (token === '\t') {
			write('\t');
		} else if (token === '\b') {
			const last = line[line.length - 1];
			if (last) last.text = last.text.slice(0, -1);
		} else if (match[2] === 'm') {
			style = applySgr(style, match[1] ?? '');
		}
	}
	write(input.slice(position));
	lines.push(renderLine(line));

	while (lines.length > 0 && lines[lines.length - 1]!.trim() === '') lines.pop();
	return { html: lines.join('\n'), lines: lines.length };
}
