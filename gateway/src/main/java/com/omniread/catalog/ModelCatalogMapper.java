package com.omniread.catalog;

import java.util.List;

import com.omniread.catalog.model.ModelCatalogEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ModelCatalogMapper {

	@Select("SELECT * FROM model_catalog WHERE status = 'active' "
			+ "AND instr(',' || plans || ',', ',' || #{plan} || ',') > 0 ORDER BY id")
	List<ModelCatalogEntity> listForPlan(@Param("plan") String plan);

	@Select("SELECT * FROM model_catalog WHERE status = 'active' AND provider = #{provider} ORDER BY id")
	List<ModelCatalogEntity> listByProvider(@Param("provider") String provider);

	@Select("SELECT * FROM model_catalog WHERE status = 'active' "
			+ "AND provider = #{provider} AND model = #{model} "
			+ "AND instr(',' || plans || ',', ',' || #{plan} || ',') > 0")
	ModelCatalogEntity findForPlan(@Param("provider") String provider, @Param("model") String model,
			@Param("plan") String plan);
}
