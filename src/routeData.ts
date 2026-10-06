import { defineRouteMiddleware, type StarlightRouteData } from '@astrojs/starlight/route-data';
import { projectOfPath } from './data/projects';
import { sectionLabel } from './sidebar.mjs';

type SidebarEntry = StarlightRouteData['sidebar'][number];

function hasCurrent(entry: SidebarEntry): boolean {
	return entry.type === 'link' ? entry.isCurrent : entry.entries.some(hasCurrent);
}

function hrefs(entries: SidebarEntry[]): string[] {
	return entries.flatMap((entry) => (entry.type === 'link' ? [entry.href] : hrefs(entry.entries)));
}

// Starlight makes a group from a sub-directory and gives it the name of the directory as its label.
function labelGroups(entries: SidebarEntry[]): void {
	for (const entry of entries) {
		if (entry.type !== 'group') continue;
		entry.label = sectionLabel(entry.label);
		labelGroups(entry.entries);
	}
}

// The sidebar config has one top-level group for each project.
// A page shows only the group of its own project, and the previous and next links stay inside it.
// A page that belongs to no project, for example the style guide, shows no sidebar.
export const onRequest = defineRouteMiddleware((context) => {
	const route = context.locals.starlightRoute;
	// A project page with no sidebar entry, for example a hidden page, has no current entry. Its path names the project.
	const project = projectOfPath(context.url.pathname);
	const group =
		route.sidebar.find((entry) => entry.type === 'group' && hasCurrent(entry)) ??
		route.sidebar.find((entry) => entry.type === 'group' && entry.label === project?.name);
	if (!group || group.type !== 'group') {
		route.sidebar = [];
		route.hasSidebar = false;
		route.pagination.prev = undefined;
		route.pagination.next = undefined;
		return;
	}

	route.sidebar = group.entries;
	// The config gives the label of each group at the top. Only the groups below them come from a sub-directory.
	for (const entry of group.entries) {
		if (entry.type === 'group') labelGroups(entry.entries);
	}
	const inProject = new Set(hrefs(group.entries));
	if (route.pagination.prev && !inProject.has(route.pagination.prev.href)) route.pagination.prev = undefined;
	if (route.pagination.next && !inProject.has(route.pagination.next.href)) route.pagination.next = undefined;
});
