/**
 * Cue developer のPRコードレビューを検証するための独立したサンプル。
 * 本番アプリから参照せず、mainにマージしない。
 * 外部通信、個人情報、APIキーなし。
 */
function averageOfScores(scores) {
  const total = scores.reduce((sum, score) => sum + score, 0);
  return total / scores.length;
}

function boundedPercentage(value) {
  return Math.round(value * 100);
}

module.exports = { averageOfScores, boundedPercentage };
