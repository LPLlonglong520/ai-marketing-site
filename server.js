const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Store data outside the deploy directory to survive redeployments
const DATA_FILE = '/tmp/site_data.json';

app.use(express.json());
app.use(express.static(__dirname));

// Load data from file
function loadData() {
  try {
    if (fs.existsSync(DATA_FILE)) {
      return JSON.parse(fs.readFileSync(DATA_FILE, 'utf-8'));
    }
  } catch (e) {
    console.error('Error loading data:', e.message);
  }
  return { likes: 0, comments: [] };
}

// Save data to file
function saveData(data) {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), 'utf-8');
  } catch (e) {
    console.error('Error saving data:', e.message);
  }
}

// GET /api/feedback — get all likes and comments
app.get('/api/feedback', (req, res) => {
  res.json(loadData());
});

// POST /api/like — toggle like
app.post('/api/like', (req, res) => {
  const data = loadData();
  const { action } = req.body; // 'add' or 'remove'
  if (action === 'add') {
    data.likes = (data.likes || 0) + 1;
  } else if (action === 'remove') {
    data.likes = Math.max(0, (data.likes || 0) - 1);
  }
  saveData(data);
  res.json({ likes: data.likes });
});

// POST /api/comment — add a comment
app.post('/api/comment', (req, res) => {
  const data = loadData();
  const { name, text } = req.body;
  if (!name || !text) {
    return res.status(400).json({ error: '姓名和内容不能为空' });
  }
  const comment = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    name: name.trim(),
    text: text.trim(),
    time: new Date().toISOString(),
  };
  data.comments = data.comments || [];
  data.comments.push(comment);
  saveData(data);
  res.json({ success: true, comment, total: data.comments.length });
});

// DELETE /api/comment/:id — delete a comment
app.delete('/api/comment/:id', (req, res) => {
  const data = loadData();
  const before = data.comments.length;
  data.comments = data.comments.filter(c => c.id !== req.params.id);
  if (data.comments.length < before) {
    saveData(data);
    res.json({ success: true });
  } else {
    res.status(404).json({ error: 'Comment not found' });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
