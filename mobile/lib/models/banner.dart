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

  String? get mainImageUrl {
    if (mediaFiles != null && mediaFiles!.isNotEmpty) {
      return mediaFiles!.first.file;
    }
    return null;
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
