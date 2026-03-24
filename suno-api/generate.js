require('dotenv').config();
const { Api } = require('suno-api');

async function generate({ prompt, lyrics, style, title, instrumental }) {
  const api = new Api(process.env.SUNO_COOKIE);

  const isCustomMode = !!lyrics;

  const payload = isCustomMode
    ? {
        prompt: lyrics,        // custom mode: prompt = 歌词
        tags: style || '',
        title: title || '',
        makeInstrumental: false,
      }
    : {
        prompt: prompt || '',  // 描述模式
        tags: style || '',
        title: title || '',
        makeInstrumental: instrumental === 'true',
      };

  console.log('生成中...', JSON.stringify(payload, null, 2));
  const clips = await api.generateClips(payload, { wait: true, waitTimeout: 300000 });

  console.log('\n✅ 生成完成:');
  clips.forEach((clip, i) => {
    console.log(`\n[${i + 1}] ${clip.title || title}`);
    console.log(`  音频: ${clip.audio_url}`);
    console.log(`  视频: ${clip.video_url}`);
    console.log(`  ID:   ${clip.id}`);
  });

  return clips;
}

const args = process.argv.slice(2);
const input = {};
args.forEach(arg => {
  const [k, ...v] = arg.split('=');
  input[k.replace('--', '')] = v.join('=');
});

generate(input).catch(err => {
  console.error('❌ 错误:', err.message || err);
  process.exit(1);
});
