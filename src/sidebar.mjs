// The sidebar of one project, made from its directory `src/content/docs/<project>/`.
// `astro.config.mjs` calls `projectSidebar` for each project, so a new page needs no change of the config.
//
// The entries, in this order:
//   1. `index.mdx` is the entry `Overview`.
//   2. Each sub-directory that holds a page is a group. The groups `install`, `use`, `develop` and `reference`
//      come first, in this order. Each other group follows, in the order of the names.
//   3. Each other page at the top of the directory is an entry, in the order of `sidebar.order` and then of the names.
// Starlight makes the entries of a group from its directory: the pages in the order of `sidebar.order`,
// and one group for each sub-directory. `src/routeData.ts` gives each such group the label of `sectionLabel`.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

// The directories of a doc set, in the order of the sidebar.
const SECTIONS = ['install', 'use', 'develop', 'reference'];

// The label of a directory whose name is not its label.
const LABELS = { commands: 'Command reference' };

const PAGE = /\.mdx?$/;

/**
 * The label of the group of one directory: `install` gives `Install`, `how-to` gives `How to`.
 * @param {string} directory The name of the directory.
 * @returns {string}
 */
export function sectionLabel(directory) {
	if (Object.hasOwn(LABELS, directory)) return LABELS[/** @type {keyof typeof LABELS} */ (directory)];
	const words = directory.replace(/[-_]+/g, ' ').trim();
	return words.charAt(0).toUpperCase() + words.slice(1);
}

/** @param {string} directory */
function holdsPage(directory) {
	return readdirSync(directory, { withFileTypes: true }).some((entry) =>
		entry.isDirectory() ? holdsPage(join(directory, entry.name)) : PAGE.test(entry.name),
	);
}

/** @param {string} a @param {string} b */
function byName(a, b) {
	return a < b ? -1 : a > b ? 1 : 0;
}

/** @param {string} a @param {string} b */
function bySection(a, b) {
	const [ia, ib] = [SECTIONS.indexOf(a), SECTIONS.indexOf(b)];
	if (ia !== ib) return (ia < 0 ? SECTIONS.length : ia) - (ib < 0 ? SECTIONS.length : ib);
	return byName(a, b);
}

/**
 * The frontmatter keys that decide the sidebar entry of a page, in the block form that the pages use.
 * A draft page and a page with `sidebar.hidden` get no entry.
 * @param {string} file
 */
function pageMeta(file) {
	const frontmatter = /^---\r?\n([\s\S]*?)\r?\n---/.exec(readFileSync(file, 'utf8'))?.[1] ?? '';
	const sidebar = /^sidebar:[ \t]*\r?\n((?:[ \t]+.*(?:\r?\n|$))*)/m.exec(frontmatter)?.[1] ?? '';
	const order = /^[ \t]+order:[ \t]*(-?\d+(?:\.\d+)?)[ \t]*$/m.exec(sidebar)?.[1];
	return {
		shown: !/^draft:[ \t]*true[ \t]*$/m.test(frontmatter) && !/^[ \t]+hidden:[ \t]*true[ \t]*$/m.test(sidebar),
		order: order === undefined ? Number.MAX_VALUE : Number(order),
	};
}

/**
 * The sidebar entries of one project.
 * @param {string} docs The path of `src/content/docs`.
 * @param {string} slug The slug of the project. It is the name of the project directory.
 * @returns {import('@astrojs/starlight/types').StarlightUserConfig['sidebar'] & {}}
 */
export function projectSidebar(docs, slug) {
	const root = join(docs, slug);
	const entries = existsSync(root) ? readdirSync(root, { withFileTypes: true }) : [];
	const files = entries.filter((entry) => entry.isFile() && PAGE.test(entry.name)).map((entry) => entry.name);
	if (!files.some((name) => name.replace(PAGE, '') === 'index')) {
		throw new Error(
			`The project "${slug}" of src/data/projects.json has no overview page. Write src/content/docs/${slug}/index.mdx.`,
		);
	}

	const groups = entries
		.filter((entry) => entry.isDirectory() && holdsPage(join(root, entry.name)))
		.map((entry) => entry.name)
		.sort(bySection)
		.map((name) => ({ label: sectionLabel(name), items: [{ autogenerate: { directory: `${slug}/${name}` } }] }));

	const pages = files
		.filter((name) => name.replace(PAGE, '') !== 'index')
		.map((name) => ({ name: name.replace(PAGE, ''), ...pageMeta(join(root, name)) }))
		.filter((page) => page.shown)
		.sort((a, b) => a.order - b.order || byName(a.name, b.name))
		.map((page) => `${slug}/${page.name}`);

	return [{ label: 'Overview', slug }, ...groups, ...pages];
}
