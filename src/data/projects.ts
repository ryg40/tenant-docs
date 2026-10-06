// The projects of the site. The home page, the project menu and the sidebar read this list.
// The data is in `projects.json`, so that a script can change it: `docgen.py register` adds a project.
// `docs: 'full'` means a complete doc set. `docs: 'overview'` means one overview page.
import data from './projects.json';

export interface Project {
	slug: string;
	name: string;
	summary: string;
	docs: 'full' | 'overview';
}

// A wrong entry stops the build here, with the position of the entry.
function checked(entry: Record<string, unknown>, index: number): Project {
	const { slug, name, summary, docs } = entry;
	const texts = [slug, name, summary].every((value) => typeof value === 'string' && value !== '');
	if (!texts || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug as string) || (docs !== 'full' && docs !== 'overview')) {
		throw new Error(
			`src/data/projects.json: entry ${index + 1} is not a project. ` +
				'It needs a `slug` in lowercase letters, digits and "-", a `name`, a `summary`, and `docs` with the value "full" or "overview".',
		);
	}
	if (data.findIndex((other) => other.slug === slug) !== index) {
		throw new Error(`src/data/projects.json: the slug "${slug}" is in the list two times.`);
	}
	return { slug, name, summary, docs } as Project;
}

export const projects: Project[] = data.map(checked);

export function projectOfPath(pathname: string): Project | undefined {
	const first = pathname.split('/').filter(Boolean)[0];
	return projects.find((project) => project.slug === first);
}
