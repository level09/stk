// @ts-check
import { readdirSync, readFileSync } from 'node:fs';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';

// llms.txt links every page's Markdown copy, read from the same files the site builds.
const docs = new URL('./src/content/docs/', import.meta.url);
const pages = readdirSync(docs)
	.filter((file) => file.endsWith('.md'))
	.map((file) => {
		const text = readFileSync(new URL(file, docs), 'utf8');
		const field = (/** @type {string} */ name) => text.match(new RegExp(`^${name}: "(.*)"$`, 'm'))?.[1];
		return `- [${field('title')}](https://docs.stkit.dev/${file}): ${field('description')}`;
	});

export default defineConfig({
	site: 'https://docs.stkit.dev',
	redirects: {
		// old Mintlify URLs
		'/introduction': '/',
		'/cursor-rules': '/ai-coding',
		// split into focused guides
		'/development': '/architecture',
	},
	integrations: [
		starlight({
			title: 'stk',
			plugins: [
				starlightLlmsTxt({
					details: [
						'In a clone, read `AGENTS.md` first: it indexes these same pages under `docs/src/content/docs/`.',
						'',
						'## Pages',
						'',
						...pages,
					].join('\n'),
				}),
			],
			description: 'An async Quart framework for developers who ship. No build tools. No configuration maze.',
			logo: { light: './src/assets/logo-light.webp', dark: './src/assets/logo-dark.webp', alt: 'stk' },
			favicon: '/favicon.ico',
			customCss: ['./src/styles/theme.css'],
			components: { PageTitle: './src/components/PageTitle.astro' },
			head: [
				{ tag: 'link', attrs: { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: true } },
				{
					tag: 'link',
					attrs: {
						rel: 'stylesheet',
						href: 'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600&display=swap',
					},
				},
			],
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/level09/stk' }],
			editLink: { baseUrl: 'https://github.com/level09/stk/edit/master/docs/' },
			sidebar: [
				{ label: 'Start', items: ['getting-started', 'build-loop', 'shell', 'ai-coding'] },
				{
					label: 'Guides',
					items: ['architecture', 'models', 'api', 'frontend', 'background-work', 'authentication', 'branding'],
				},
				{ label: 'Reference', items: ['cli', 'configuration'] },
				{ label: 'Deploy', items: ['deployment'] },
			],
		}),
	],
});
