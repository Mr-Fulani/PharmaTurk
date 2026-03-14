import 'package:json_annotation/json_annotation.dart';

part 'banner.g.dart';

@JsonSerializable()
class Banner {
  final int id;
  final String title;
  final String? description;
  final String position;
  @JsonKey(name: 'link_url')
  final String? linkUrl;
  @JsonKey(name: 'link_text')
  final String? linkText;
  @JsonKey(name: 'is_active', defaultValue: true)
  final bool isActive;
  @JsonKey(name: 'sort_order')
  final int sortOrder;
  @JsonKey(name: 'media_files')
  final List<BannerMediaFile>? mediaFiles;

  Banner({
    required this.id,
    required this.title,
    this.description,
    required this.position,
    this.linkUrl,
    this.linkText,
    required this.isActive,
    required this.sortOrder,
    this.mediaFiles,
  });

  factory Banner.fromJson(Map<String, dynamic> json) => _$BannerFromJson(json);
  Map<String, dynamic> toJson() => _$BannerToJson(this);

  /// Первое изображение (не видео). CachedNetworkImage не поддерживает .mp4.
  static bool _isVideoUrl(String? url) {
    if (url == null || url.isEmpty) return false;
    final path = url.split('?').first.toLowerCase();
    return path.endsWith('.mp4') || path.endsWith('.webm') || path.endsWith('.mov') ||
        path.endsWith('.m4v') || path.endsWith('.mkv');
  }

  String? get mainImageUrl {
    if (mediaFiles == null || mediaFiles!.isEmpty) return null;
    for (final m in mediaFiles!) {
      if (!_isVideoUrl(m.file)) return m.file;
    }
    return mediaFiles!.first.file;
  }
}

@JsonSerializable()
class BannerMediaFile {
  final int id;
  final String file;
  final String? title;
  final String? description;
  @JsonKey(name: 'sort_order')
  final int sortOrder;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;

  BannerMediaFile({
    required this.id,
    required this.file,
    this.title,
    this.description,
    required this.sortOrder,
    required this.createdAt,
  });

  factory BannerMediaFile.fromJson(Map<String, dynamic> json) => _$BannerMediaFileFromJson(json);
  Map<String, dynamic> toJson() => _$BannerMediaFileToJson(this);
}
