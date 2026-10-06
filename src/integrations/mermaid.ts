// Renders each fenced `mermaid` block to inline SVG at build time. No browser and no client script.
// The renderer is `beautiful-mermaid`. It supports flowcharts, state, sequence, class and ER diagrams, and XY charts.
// A block of another type stops the build.
//
// A flowchart or a state diagram that is too wide for a narrow column gets a second render: the narrow form.
// A narrow column shows the narrow form when the wide form does not fit there with labels of 11 px.
// The renderer has some faults. The functions below correct them in the source or in the SVG, after the render.
import type { AstroIntegration } from 'astro';
import type { Element } from 'hast';
import { parseMermaid, renderMermaidSVG } from 'beautiful-mermaid';
import type { MermaidGraph, RenderOptions } from 'beautiful-mermaid';

// The SVG reads these tokens from the page, so the diagram follows `src/styles/soft-night.css`.
const COLORS = {
	bg: 'var(--sn-panel)',
	fg: 'var(--sn-ink)',
	line: 'var(--sn-faint)',
	accent: 'var(--sn-sea)',
	muted: 'var(--sn-muted)',
	surface: 'var(--sn-raise)',
	border: 'var(--sn-diagram-edge)',
};

// A wide diagram becomes smaller down to this part of its size. Below that, it scrolls sideways.
const MIN_SCALE = 0.75;
// In a narrow column, no label becomes smaller than this size in px. Below that, the diagram scrolls sideways.
const MIN_LABEL = 11;
// The width of the page column in px, at a screen width of 360 px and at a screen width of 320 px.
const NARROW_FIT = 310;
const SMALLEST_COLUMN = 270;
// A column is narrow up to this width in px. The container query in `src/styles/components.css` has the same value.
// The page column at a screen width of 1440 px is wider, so that view does not change.
const NARROW_COLUMN = 640;
// The narrow form of a diagram has less space around the nodes and between them.
const COMPACT: RenderOptions = { padding: 8, nodeSpacing: 16, layerSpacing: 32 };

interface Alternative {
	title: string;
	caption?: string;
	summary?: string;
}

// One render of a diagram. `narrow` is its smallest width in a narrow column.
interface Form {
	svg: string;
	width: number;
	narrow: number;
}

function escapeHtml(text: string): string {
	return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// A label as one line of page text.
function plain(label: string): string {
	return escapeHtml(label.replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim());
}

// Mermaid has the lines `accTitle:` and `accDescr:` for the text alternative. The renderer does not read them.
function splitSource(code: string, meta: string): { source: string; alternative: Alternative } {
	let title: string | undefined;
	let summary: string | undefined;
	const source = code
		.replace(/^[ \t]*accDescr[ \t]*\{([^}]*)\}[ \t]*$/m, (_, text: string) => {
			summary = text.trim().replace(/\s+/g, ' ');
			return '';
		})
		.split('\n')
		.filter((line) => {
			const match = line.match(/^\s*(accTitle|accDescr)\s*:\s*(.+)$/);
			if (!match) return true;
			if (match[1] === 'accTitle') title = match[2]!.trim();
			else summary = match[2]!.trim();
			return false;
		})
		.join('\n');
	const caption = meta.match(/title="([^"]*)"/)?.[1];
	return { source, alternative: { title: title ?? caption ?? 'Diagram', caption, summary } };
}

// The lines of a sequence diagram, as the parser of the renderer reads them.
const ACTOR_LINE = /^(?:participant|actor)\s+(\S+?)(?:\s+as\s+(.+))?$/;
const NOTE_LINE = /^Note\s+(?:left of|right of|over)\s+([^:]+):\s*(.+)$/i;
const BLOCK_LINE = /^(?:loop|alt|opt|par|critical|break|rect)/;
const MESSAGE_LINE = /^(\S+?)\s*(?:--?>?>|--?[)x]|--?>>|--?>)\s*[+-]?(\S+?)\s*:\s*(.+)$/;

// The text form of the diagram: one line for each arrow and each note, in the order of the source.
function listSteps(source: string): { steps: string[]; arrows: number } | undefined {
	if (/^\s*sequenceDiagram/.test(source)) {
		const names = new Map<string, string>();
		const name = (id: string) => `<b>${plain(names.get(id) ?? id)}</b>`;
		const steps: string[] = [];
		let arrows = 0;
		for (const line of source.split('\n').map((text) => text.trim())) {
			const actor = line.match(ACTOR_LINE);
			if (actor) names.set(actor[1]!, (actor[2] ?? actor[1]!).trim());
			const note = line.match(NOTE_LINE);
			if (note) {
				const actors = note[1]!.split(',').map((id) => name(id.trim()));
				steps.push(`Note for ${actors.join(' and ')}: ${plain(note[2]!)}`);
				continue;
			}
			const message = line.match(MESSAGE_LINE);
			if (message) {
				steps.push(`${name(message[1]!)} to ${name(message[2]!)}: ${plain(message[3]!)}`);
				arrows += 1;
			}
		}
		return steps.length > 0 ? { steps, arrows } : undefined;
	}
	try {
		const graph = parseMermaid(source);
		// An arrow can start or end at a subgraph. The parser then makes a node that has the id as its label.
		const groups = new Map<string, string>();
		const collect = (list: MermaidGraph['subgraphs']) => {
			for (const group of list) {
				groups.set(group.id, group.label);
				collect(group.children);
			}
		};
		collect(graph.subgraphs);
		const label = (id: string) => {
			const node = graph.nodes.get(id);
			if (node?.shape === 'state-start') return 'Start';
			if (node?.shape === 'state-end') return 'End';
			return plain(groups.get(id) ?? node?.label ?? id);
		};
		const steps = graph.edges.map((edge) => {
			const verb = !edge.hasArrowEnd ? 'connects to' : edge.hasArrowStart ? 'goes to and from' : 'goes to';
			const note = edge.label ? ` (${plain(edge.label)})` : '';
			return `<b>${label(edge.source)}</b> ${verb} <b>${label(edge.target)}</b>${note}`;
		});
		return steps.length > 0 ? { steps, arrows: steps.length } : undefined;
	} catch {
		// Not a flowchart or a state diagram. The text form is the source.
		return undefined;
	}
}

// A sequence diagram with a note before the first message, with a placeholder message before that note.
// It is `undefined` when the diagram has no such note.
function withPlaceholder(source: string): string | undefined {
	const lines = source.split('\n');
	const known: string[] = [];
	let block = -1;
	for (const [index, text] of lines.entries()) {
		const line = text.trim();
		const actor = line.match(ACTOR_LINE);
		if (actor) {
			known.push(actor[1]!);
			continue;
		}
		const note = line.match(NOTE_LINE);
		if (note) {
			// The placeholder must not change the order of the participants, and it must not be a loop.
			const [from, second] = note[1]!.split(',').map((id) => id.trim());
			const to = second ?? known.find((id) => id !== from) ?? from;
			// A block that starts before the note must not start at the placeholder.
			lines.splice(block < 0 ? index : block, 0, `${from}->>${to}: .`);
			return lines.join('\n');
		}
		if (block < 0 && BLOCK_LINE.test(line)) block = index;
		else if (MESSAGE_LINE.test(line)) return undefined;
	}
	return undefined;
}

// The renderer does not draw a note before the first message of a sequence diagram. Its parser gives the
// note the message index -1, and its layout places a note only below a message that exists.
// So a placeholder message goes before the note, and the renderer draws the note below the placeholder.
// Then this function removes the placeholder and moves the lower part of the diagram up.
function renderSequence(source: string, options: RenderOptions): string {
	const patched = withPlaceholder(source);
	if (!patched) return renderMermaidSVG(source, options);

	let svg = renderMermaidSVG(patched, options);
	const placeholder = svg.match(/<g class="message"[^>]*>[\s\S]*?<\/g>\n?/);
	const top = svg.match(/<line class="lifeline"[^>]*\sy1="([\d.]+)"/);
	const note = svg.match(/<g class="note"[^>]*>\s*<polygon points="[\d.-]+,([\d.-]+)/);
	const box = /^(<svg [^>]*viewBox="0 0 [\d.]+ )([\d.]+)(" width="[\d.]+" height=")\2"/;
	if (!placeholder || !top || !note || !box.test(svg)) {
		throw new Error('The correction for a note before the first message does not fit the SVG of the renderer.');
	}
	svg = svg.replace(placeholder[0], '');

	// The name of an `actor` participant is below its symbol, so the note starts lower.
	const gap = svg.includes('data-type="actor"') ? 28 : 12;
	const up = Number(note[1]) - (Number(top[1]) + gap);
	if (up <= 0) return svg;
	const less = (value: string) => String(Number(value) - up);
	return svg
		.replace(/<(g class="(?:block|message|note)"|rect class="activation")/g, `<$1 transform="translate(0,-${up})"`)
		.replace(/(<line class="lifeline"[^>]*\sy2=")([\d.]+)"/g, (_, start: string, y: string) => `${start}${less(y)}"`)
		.replace(box, (_, start: string, height: string, middle: string) => `${start}${less(height)}${middle}${less(height)}"`);
}

// The width of a text in px. This is an estimate: the build has no font.
// The numbers agree with the widths of the subgraph titles of the site in a browser, to 3 %.
function textWidth(text: string, size: number): number {
	let em = 0;
	for (const char of text.replace(/&[a-z]+;/g, 'x')) {
		if (/[\sijl.,:;'|!]/.test(char)) em += 0.27;
		else if (/[ftr()[\]/-]/.test(char)) em += 0.36;
		else if (/[mwMW@%]/.test(char)) em += 0.82;
		else if (/[A-Z]/.test(char)) em += 0.62;
		else em += 0.53;
	}
	return em * size;
}

// The renderer does not make a subgraph as wide as its title, so a long title leaves the box.
// A title that is too wide goes on two lines, and the title band becomes higher.
function wrapGroupTitles(svg: string): string {
	// The box of the subgraph, its title band, and the title as one line of text.
	const title = new RegExp(
		'(<g class="subgraph"[^>]*>\\s*<rect x="[\\d.-]+" y="[\\d.-]+" width="([\\d.]+)"[^>]*/>' +
			'\\s*<rect [^>]*?height=")[\\d.]+("[^>]*/>' +
			'\\s*<text x="([\\d.-]+)" [^>]*?font-size="([\\d.]+)"[^>]*?) dy="[\\d.-]+">([^<]*)</text>',
		'g'
	);
	return svg.replace(title, (all, start: string, width: string, middle: string, x: string, size: string, label: string) => {
		// The title starts 12px from the left side of the box. It must end 4px or more before the right side.
		const room = Number(width) - 16;
		const words = label.split(' ');
		if (words.length < 2 || textWidth(label, Number(size)) <= room) return all;
		// The two lines are as equal in width as the words permit.
		const lines = (at: number) => [words.slice(0, at).join(' '), words.slice(at).join(' ')];
		const longer = (at: number) => Math.max(...lines(at).map((line) => textWidth(line, 1)));
		let best = 1;
		for (let at = 2; at < words.length; at++) if (longer(at) < longer(best)) best = at;
		const [first, second] = lines(best);
		return (
			`${start}38${middle}>` +
			`<tspan x="${x}" dy="1.5">${first}</tspan><tspan x="${x}" dy="15">${second}</tspan></text>`
		);
	});
}

// The renderer has no arrow with a cross or a circle at its end. It draws a node with the name `x` or `o`
// and drops the rest of the line. The build stops, because the diagram then shows wrong content.
function checkArrows(source: string): void {
	for (const line of source.split('\n')) {
		if (/(?:--|-\.-|\.-|==)[xo](?=[\s|]|$)/.test(line.replace(/"[^"]*"/g, '""'))) {
			throw new Error(
				`The renderer has no arrow with a cross or a circle: "${line.trim()}". ` +
					'Use an arrow without one, for example `-.-`. Put a space before a node with the name `x` or `o`.'
			);
		}
	}
}

// One render of the source, with the corrections for the faults of the renderer.
function render(source: string, layout: RenderOptions = {}): Form {
	const options = { ...COLORS, transparent: true, ...layout };
	const first = source.trim().split(/[\n;]/)[0]!.trim();
	if (/^(?:flowchart|graph)\s/i.test(first)) checkArrows(source);
	let svg = /^sequenceDiagram$/i.test(first) ? renderSequence(source, options) : renderMermaidSVG(source, options);

	// The renderer turns the start head of a two-way arrow into its node, and the node hides that head.
	svg = svg.replace(/(<marker id="arrowhead-start[^"]*"[^>]*\sorient=")auto-start-reverse"/g, '$1auto"');
	svg = wrapGroupTitles(svg);

	const width = Number(svg.match(/^<svg[^>]*\swidth="([\d.]+)"/)?.[1] ?? 0);
	const sizes = [...svg.matchAll(/\sfont-size="([\d.]+)"/g)].map((match) => Number(match[1]));
	const scale = sizes.length > 0 ? Math.max(MIN_SCALE, MIN_LABEL / Math.min(...sizes)) : MIN_SCALE;
	return { svg, width, narrow: Math.ceil(width * scale) };
}

// The same flowchart or state diagram from the top to the bottom.
function tallSource(source: string): string {
	return source
		.replace(/^(\s*(?:flowchart|graph)\s+)(?:LR|RL)\b/im, '$1TD')
		.replace(/^(\s*direction\s+)(?:LR|RL)\s*$/gim, '$1TB');
}

// The form of a diagram for a narrow column. It is `undefined` when the usual form is good there too.
// Only the layout of a flowchart and of a state diagram has options.
function renderNarrow(source: string, wide: Form): Form | undefined {
	const first = source.trim().split(/[\n;]/)[0]!.trim();
	if (wide.narrow <= NARROW_FIT || !/^(?:flowchart|graph|stateDiagram)/i.test(first)) return undefined;
	let best = render(source, COMPACT);
	const tall = tallSource(source);
	if (tall !== source) {
		const form = render(tall, COMPACT);
		// The tall form must fit when the compact form does not, or it must be clearly less wide.
		const fits = form.narrow <= NARROW_FIT && best.narrow > NARROW_FIT;
		if (fits || form.narrow < best.narrow * 0.95) best = form;
	}
	return best.narrow < wide.narrow * 0.95 ? best : undefined;
}

let count = 0;

// Makes the SVG of one form a part of the page. `swap` is the widest column that shows the narrow form.
function finish(form: Form, prefix: string, alternative: Alternative, summary?: string, role = '', swap = 0): string {
	let svg = form.svg;
	// A diagram with two forms: the wide form shows first, and a column of the width `swap` or less changes that.
	if (role) {
		const display = role === 'narrow' ? 'block' : 'none';
		svg = svg.replace(
			'</style>',
			`  @container sn-diagram (max-width: ${swap}px) { #${prefix} { display: ${display}; } }\n</style>`
		);
	}
	// The renderer adds a web font import. The site makes no request to another origin, so the import goes.
	svg = svg.replace(/^\s*@import url\([^)]*\);[ \t]*\n/gm, '');
	// The style rules of the renderer must apply to this diagram only, and the text takes the font of the site.
	svg = svg.replace(/^(\s*)text \{[^}]*\}/m, `$1#${prefix} text { font-family: inherit; }`);
	svg = svg.replace(/^(\s*)svg \{/m, `$1#${prefix} {`);
	// An id must be unique in the page.
	const ids = [...svg.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]!);
	for (const id of new Set(ids)) {
		svg = svg.replaceAll(`id="${id}"`, `id="${prefix}-${id}"`).replaceAll(`url(#${id})`, `url(#${prefix}-${id})`);
	}

	const describedBy = summary ? ` aria-describedby="${prefix}-desc"` : '';
	const classes = role ? ` class="sn-diagram-${role}"` : '';
	// The style rules of the diagram read these two widths.
	const widths = `--sn-diagram-min:${Math.round(form.width * MIN_SCALE)}px;--sn-diagram-min-narrow:${form.narrow}px`;
	svg = svg.replace(
		/^<svg ([^>]*)style="([^"]*)">/,
		(_, attributes: string, style: string) =>
			`<svg id="${prefix}"${classes} role="img" aria-labelledby="${prefix}-title"${describedBy} ${attributes}` +
			`style="${style};${widths}">` +
			`<title id="${prefix}-title">${escapeHtml(alternative.title)}</title>` +
			(summary ? `<desc id="${prefix}-desc">${escapeHtml(summary)}</desc>` : '')
	);

	if (/https?:\/\/(?!www\.w3\.org\/)/.test(svg)) {
		throw new Error('The diagram SVG holds a URL of another origin.');
	}
	return svg.replace(/\n\s*/g, ' ');
}

function renderDiagram(code: string, meta: string): string {
	const { source, alternative } = splitSource(code, meta);
	const prefix = `dg${++count}`;
	const wide = render(source);
	let narrow: Form | undefined;
	try {
		narrow = renderNarrow(source, wide);
	} catch (error) {
		throw new Error(`the form for a narrow screen: ${error instanceof Error ? error.message : error}`);
	}

	const list = listSteps(source);
	const summary =
		alternative.summary ??
		(list ? `${list.arrows} connections. The list "Diagram as text" below the diagram gives each one.` : undefined);
	const text = list
		? `<ol>${list.steps.map((step) => `<li>${step}</li>`).join('')}</ol>`
		: `<pre><code>${escapeHtml(source.trim())}</code></pre>`;
	// A diagram that can scroll sideways must take the keyboard focus.
	const scrolls = (narrow ?? wide).narrow > SMALLEST_COLUMN || wide.width * MIN_SCALE > NARROW_COLUMN;
	const view = scrolls
		? `<div class="sn-diagram-view" tabindex="0" role="group" aria-label="${escapeHtml(alternative.title)}">`
		: '<div class="sn-diagram-view">';
	// The wide form shows in each column where it fits with labels of `MIN_LABEL`, and in each column that is not narrow.
	const swap = Math.min(wide.narrow - 1, NARROW_COLUMN);
	const forms = narrow
		? finish(wide, prefix, alternative, summary, 'wide', swap) +
			finish(narrow, `${prefix}n`, alternative, summary, 'narrow', swap)
		: finish(wide, prefix, alternative, summary);
	return (
		'<figure class="sn-diagram not-content">' +
		view +
		forms +
		'</div>' +
		(alternative.caption ? `<figcaption>${escapeHtml(alternative.caption)}</figcaption>` : '') +
		`<details class="sn-diagram-text"><summary>Diagram as text</summary>${text}</details>` +
		'</figure>'
	);
}

function mermaidPlugin() {
	return {
		name: 'tenant-docs-mermaid',
		element: {
			filter: ['pre'],
			visit(node: Readonly<Element>) {
				const [code, ...rest] = node.children;
				if (rest.length > 0 || code?.type !== 'element' || code.tagName !== 'code') return;
				const data = code.data as { lang?: string; meta?: string } | undefined;
				const [text] = code.children;
				if (data?.lang !== 'mermaid' || text?.type !== 'text') return;
				try {
					return { type: 'raw' as const, value: renderDiagram(text.value, data.meta ?? '') };
				} catch (error) {
					// A diagram that shows as code is a defect, so the build stops.
					throw new Error(`[mermaid] A diagram does not render: ${error instanceof Error ? error.message : error}`);
				}
			},
		},
	};
}

interface PluginHost {
	name: string;
	options: { hastPlugins: unknown[] };
}

export default function mermaid(): AstroIntegration {
	return {
		name: 'tenant-docs-mermaid',
		hooks: {
			'astro:config:setup': ({ config }) => {
				const processor = config.markdown.processor as PluginHost | undefined;
				if (processor?.name !== 'satteri') {
					throw new Error('The Mermaid integration needs the default Markdown processor of Astro (satteri).');
				}
				// First in the list: the diagram must be gone before Expressive Code reads the code blocks.
				processor.options.hastPlugins.unshift(mermaidPlugin);
			},
		},
	};
}
