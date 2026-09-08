import { isVideoFile, VIDEO_ACCEPT } from './caseConstants';

const makeFile = ({ name, type = 'application/octet-stream', size = 100 }) => ({
  name,
  type,
  size,
});

describe('case media constraints', () => {
  it('accepts supported recording containers and audio files', () => {
    expect(isVideoFile(makeFile({ name: 'exam.mp4', type: 'video/mp4' }))).toBe(true);
    expect(isVideoFile(makeFile({ name: 'exam.mov', type: 'video/quicktime' }))).toBe(true);
    expect(isVideoFile(makeFile({ name: 'exam.webm', type: 'video/webm' }))).toBe(true);
    expect(isVideoFile(makeFile({ name: 'audio.m4a', type: 'audio/mp4' }))).toBe(true);
  });

  it('rejects containers that the production transcription path cannot complete', () => {
    expect(isVideoFile(makeFile({ name: 'exam.mpg', type: 'video/mpeg' }))).toBe(false);
    expect(isVideoFile(makeFile({ name: 'exam.avi', type: 'video/x-msvideo' }))).toBe(false);
    expect(isVideoFile(makeFile({ name: 'exam.mkv', type: 'video/x-matroska' }))).toBe(false);
    expect(VIDEO_ACCEPT).not.toContain('.mpg');
    expect(VIDEO_ACCEPT).not.toContain('.avi');
    expect(VIDEO_ACCEPT).not.toContain('.mkv');
  });
});
