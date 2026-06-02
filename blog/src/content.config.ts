import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

function removeDupsAndLowerCase(array: string[]) {
  if (!array.length) return array;
  const lowercaseItems = array.map((str) => str.toLowerCase());
  const distinctItems = new Set(lowercaseItems);
  return Array.from(distinctItems);
}

const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: ({ image }) =>
    z.object({
      title: z.string().max(120),
      description: z.string().min(10).max(160),
      pubDate: z
        .string()
        .or(z.date())
        .transform((val) => new Date(val)),
      lang: z.string(),
      tags: z.array(z.string()).default([]).transform(removeDupsAndLowerCase),
      caseSlug: z.string().optional(),
      coverImage: z
        .object({
          alt: z.string(),
          src: image(),
        })
        .optional(),
      draft: z.boolean().default(false),
      ogImage: z.string().optional(),
    }),
});

export const collections = { blog };
