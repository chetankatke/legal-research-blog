import { type CollectionEntry, getCollection } from "astro:content";
import { siteConfig } from "@/site-config";

/** Fetch all posts from the 'blog' collection. Drafts are excluded in production builds. */
export async function getAllPosts(): Promise<CollectionEntry<"blog">[]> {
	return await getCollection("blog", ({ data }) => {
		return import.meta.env.PROD ? !data.draft : true;
	});
}

/** Derive a clean slug by stripping the two-letter language prefix from post.id. */
export function getPostSlug(post: CollectionEntry<"blog">): string {
	return post.id.replace(/^[a-z]{2}\//, "");
}

/** Date used for sorting — `updatedDate` if `siteConfig.sortPostsByUpdatedDate`, else `pubDate`. */
export function getPostSortDate(post: CollectionEntry<"blog">): Date {
	return siteConfig.sortPostsByUpdatedDate && post.data.updatedDate !== undefined
		? new Date(post.data.updatedDate)
		: new Date(post.data.pubDate);
}

/** Sort by `getPostSortDate`, newest first. Mutates input. */
export function sortMDByDate(posts: CollectionEntry<"blog">[]): CollectionEntry<"blog">[] {
	return posts.sort((a, b) => {
		const aDate = getPostSortDate(a).valueOf();
		const bDate = getPostSortDate(b).valueOf();
		return bDate - aDate;
	});
}
