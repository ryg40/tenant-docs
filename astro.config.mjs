// @ts-check
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { projects } from './src/data/projects.ts';
import mermaid from './src/integrations/mermaid.ts';
import { projectSidebar } from './src/sidebar.mjs';

// One top-level sidebar group for each project. The entries of a group come from the directory of the project:
// see `src/sidebar.mjs`. `src/routeData.ts` shows only the group of the current project.
const docs = fileURLToPath(new URL('./src/content/docs', import.meta.url));

const sidebar = projects.map((project) => ({
	label: project.name,
	items: projectSidebar(docs, project.slug),
}));

// The public origin is a deploy value. It comes from `.env`, not from the tracked files.
const site = process.env.SITE_URL || undefined;

// A link preview needs an absolute image address. With no `SITE_URL`, the address stays relative.
const ogImage = site ? new URL('/og.png', site).href : '/og.png';

// https://astro.build/config
export default defineConfig({
	site,
	integrations: [
		// Renders each fenced `mermaid` block to inline SVG at build time.
		mermaid(),
		starlight({
			title: 'Tenant Docs',
			description: 'Guides for the tenant projects: how to develop, install and use each one.',
			customCss: ['./src/styles/soft-night.css', './src/styles/components.css'],
			favicon: '/favicon.svg',
			head: [
				{ tag: 'meta', attrs: { name: 'theme-color', content: '#151e2c' } },
				{ tag: 'meta', attrs: { property: 'og:image', content: ogImage } },
				{ tag: 'meta', attrs: { property: 'og:image:type', content: 'image/png' } },
				{ tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
				{ tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
				{ tag: 'meta', attrs: { property: 'og:image:alt', content: 'Tenant Docs. Guides for the tenant projects.' } },
				{ tag: 'meta', attrs: { name: 'twitter:image', content: ogImage } },
			],
			routeMiddleware: './src/routeData.ts',
			components: {
				Header: './src/components/Header.astro',
				PageTitle: './src/components/PageTitle.astro',
				ThemeProvider: './src/components/ThemeProvider.astro',
				ThemeSelect: './src/components/ThemeSelect.astro',
			},
			expressiveCode: {
				themes: ['github-dark-dimmed'],
				styleOverrides: {
					borderRadius: '10px',
					borderColor: 'var(--sn-rule)',
					// The syntax theme gives a blue to the focus ring and to the marked lines.
					focusBorder: 'var(--sn-sea)',
					textMarkers: {
						// Marked: navy. Inserted: mint. Deleted: coral. The values are the Soft Night tokens.
						markBackground: '#2a3a52',
						markBorderColor: '#98a8bb',
						insBackground: '#1f3b3f',
						insBorderColor: '#86d6c6',
						insDiffIndicatorColor: '#a9e6da',
						delBackground: '#402b2d',
						delBorderColor: '#f59c86',
						delDiffIndicatorColor: '#ffb9a8',
					},
					codeBackground: 'var(--sn-well)',
					frames: {
						editorActiveTabBackground: 'var(--sn-well)',
						editorTabBarBackground: 'var(--sn-band)',
						terminalBackground: 'var(--sn-well)',
						terminalTitlebarBackground: 'var(--sn-band)',
						frameBoxShadowCssValue: 'none',
					},
				},
			},
			sidebar,
		}),
	],
});
