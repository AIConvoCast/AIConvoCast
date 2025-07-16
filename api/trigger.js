export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ message: 'Method not allowed' });
  }

  const GITHUB_TOKEN = process.env.GH_TOKEN; // Use your existing variable name
  const repo = 'AIConvoCast/AIConvoCast'; // Your repo
  const workflow_id = 'ai_podcast_pipeline.yml'; // Your workflow file name
  const ref = 'main';

  const response = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/${workflow_id}/dispatches`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github+json'
    },
    body: JSON.stringify({ ref })
  });

  if (response.ok) {
    res.status(200).json({ message: 'Workflow triggered successfully!' });
  } else {
    const error = await response.text();
    res.status(500).json({ message: 'Failed to trigger workflow', error });
  }
} 