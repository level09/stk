import type { APIRoute, GetStaticPaths } from 'astro';
import { getCollection } from 'astro:content';

export const getStaticPaths: GetStaticPaths = async () =>
	(await getCollection('docs', (entry) => entry.id !== 'index')).map((entry) => ({
		params: { slug: entry.id },
		props: { entry },
	}));

export const GET: APIRoute = ({ props }) =>
	new Response(`# ${props.entry.data.title}\n\n${props.entry.body}`, {
		headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
	});
