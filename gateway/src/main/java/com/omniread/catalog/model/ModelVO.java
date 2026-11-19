package com.omniread.catalog.model;

public record ModelVO(String provider, String model, String displayName) {

	public static ModelVO of(ModelCatalogEntity entity) {
		return new ModelVO(entity.getProvider(), entity.getModel(), entity.getDisplayName());
	}
}
