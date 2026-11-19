package com.omniread.catalog.model;

/** model_catalog 表行；plans 为逗号分隔的可用档位。 */
public class ModelCatalogEntity {

	private Long id;
	private String provider;
	private String model;
	private String displayName;
	private String plans;
	private Integer byokSupported;
	private String status;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public String getProvider() {
		return provider;
	}

	public void setProvider(String provider) {
		this.provider = provider;
	}

	public String getModel() {
		return model;
	}

	public void setModel(String model) {
		this.model = model;
	}

	public String getDisplayName() {
		return displayName;
	}

	public void setDisplayName(String displayName) {
		this.displayName = displayName;
	}

	public String getPlans() {
		return plans;
	}

	public void setPlans(String plans) {
		this.plans = plans;
	}

	public Integer getByokSupported() {
		return byokSupported;
	}

	public void setByokSupported(Integer byokSupported) {
		this.byokSupported = byokSupported;
	}

	public String getStatus() {
		return status;
	}

	public void setStatus(String status) {
		this.status = status;
	}
}
