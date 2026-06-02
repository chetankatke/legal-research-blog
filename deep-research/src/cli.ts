import * as fs from 'fs/promises';
import { getModel } from './ai/providers';
import { deepResearch, writeFinalReport, writeFinalAnswer } from './deep-research';

// Non-interactive CLI for deep-research
// Usage: tsx --env-file=.env.local src/cli.ts
// Environment variables:
//   QUERY - research question
//   BREADTH - research breadth (default: 4)
//   DEPTH - research depth (default: 2)
//   TYPE - "report" or "answer" (default: "report")

async function run() {
  const query = process.env.QUERY;
  if (!query) {
    console.error('ERROR: QUERY environment variable is required');
    process.exit(1);
  }

  const breadth = parseInt(process.env.BREADTH || '4', 10);
  const depth = parseInt(process.env.DEPTH || '2', 10);
  const outputType = (process.env.TYPE || 'report') as 'report' | 'answer';

  console.log('Using model:', getModel().modelId);
  console.log(`Research query: ${query.slice(0, 80)}...`);
  console.log(`Breadth: ${breadth}, Depth: ${depth}, Type: ${outputType}`);
  console.log('');

  const combinedQuery = query;

  console.log('Starting research...\n');

  const { learnings, visitedUrls } = await deepResearch({
    query: combinedQuery,
    breadth,
    depth,
  });

  console.log(`\n\nLearnings:\n\n${learnings.join('\n')}`);
  console.log(`\n\nVisited URLs (${visitedUrls.length}):\n\n${visitedUrls.join('\n')}`);
  console.log('Writing final report...');

  if (outputType === 'report') {
    const report = await writeFinalReport({
      prompt: combinedQuery,
      learnings,
      visitedUrls,
    });

    await fs.writeFile('report.md', report, 'utf-8');
    console.log(`\n\nFinal Report:\n\n${report}`);
    console.log('\nReport has been saved to report.md');
  } else {
    const answer = await writeFinalAnswer({
      prompt: combinedQuery,
      learnings,
    });

    await fs.writeFile('answer.md', answer, 'utf-8');
    console.log(`\n\nFinal Answer:\n\n${answer}`);
    console.log('\nAnswer has been saved to answer.md');
  }
}

run().catch((err) => {
  console.error('Error:', err);
  process.exit(1);
});
